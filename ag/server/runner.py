"""Program execution engine — runs code from the Monaco editor.

Three execution modes:
  python   → asyncio subprocess, stdout/stderr streamed as SSE
  node     → same, via node.js if installed
  bash     → same, via /bin/bash
  html     → write to temp file, return a serve URL (iframe in UI)

GUI support (Pygame, Tkinter, etc.):
  DISPLAY is passed through from the server process environment.
  If the user has a desktop session, GUI windows open normally.
  If headless, they'll get a display error — we surface that cleanly.

Process lifecycle:
  - Each run returns a PID.
  - The UI can send POST /api/run/kill with {pid} to terminate.
  - Output is capped at MAX_OUTPUT_LINES to prevent scroll flooding.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator


_SANDBOX_DIR = Path(tempfile.gettempdir()) / "ag_run"
_SANDBOX_DIR.mkdir(exist_ok=True)

MAX_OUTPUT_LINES = 2000
OUTPUT_TIMEOUT_S = 120   # kill after 2 min with no activity (not wall time)

# ── Running process registry ──────────────────────────────────────────────────
# pid → asyncio.subprocess.Process
_running: dict[int, asyncio.subprocess.Process] = {}


def kill_process(pid: int) -> dict:
    """Kill a running process by PID.

    Returns:
        {"ok": True} or {"ok": False, "error": "..."}
    """
    proc = _running.get(pid)
    if proc is None:
        return {"ok": False, "error": f"No process with PID {pid}"}
    try:
        proc.kill()
        _running.pop(pid, None)
        return {"ok": True}
    except ProcessLookupError:
        _running.pop(pid, None)
        return {"ok": True}   # already exited


def save_html(code: str, filename: str = "output.html") -> Path:
    """Write HTML code to the sandbox directory and return the path."""
    dest = _SANDBOX_DIR / filename
    dest.write_text(code, encoding="utf-8")
    return dest


async def run_code(
    code: str,
    language: str,
    filename: str = "main",
) -> AsyncIterator[dict]:
    """Execute code and stream output events.

    Yields dicts with keys:
      {"type": "stdout"|"stderr"|"system"|"exit", "data": str, "pid": int}

    Args:
        code: Source code to execute.
        language: One of "python", "javascript", "bash", "html".
        filename: Used for HTML file naming.
    """
    language = language.lower()

    # ── HTML: save and serve, don't subprocess ────────────────────────────────
    if language in ("html", "markdown"):
        path = save_html(code, f"{filename}.html")
        yield {
            "type": "system",
            "data": f"✅ HTML saved — open at /run/{path.name}",
            "pid": 0,
            "url": f"/run/{path.name}",
        }
        return

    # ── Build the command ─────────────────────────────────────────────────────
    cmd, script_path = _build_command(code, language, filename)
    if cmd is None:
        yield {"type": "system", "data": f"❌ Cannot run language: {language}", "pid": 0}
        return

    yield {"type": "system", "data": f"$ {' '.join(cmd)}", "pid": 0}

    # ── Launch subprocess ─────────────────────────────────────────────────────
    env = {**os.environ}   # Pass DISPLAY, PATH, HOME etc.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(_SANDBOX_DIR),
            env=env,
        )
    except FileNotFoundError as exc:
        yield {"type": "system", "data": f"❌ {exc}", "pid": 0}
        return

    pid = proc.pid
    _running[pid] = proc
    yield {"type": "system", "data": f"⏳ Process started (PID {pid})", "pid": pid}

    # ── Stream stdout and stderr concurrently via shared Queue ────────────────
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    lines_emitted = 0

    async def _pump(stream: asyncio.StreamReader, kind: str) -> None:
        """Feed lines from stream into the queue; send None sentinel when done."""
        while True:
            try:
                line = await asyncio.wait_for(stream.readline(), timeout=OUTPUT_TIMEOUT_S)
            except asyncio.TimeoutError:
                break
            if not line:
                break
            await queue.put({"type": kind, "data": line.decode(errors="replace").rstrip("\n"), "pid": pid})
        await queue.put(None)  # sentinel

    tasks = [
        asyncio.create_task(_pump(proc.stdout, "stdout")),
        asyncio.create_task(_pump(proc.stderr, "stderr")),
    ]

    sentinels_received = 0
    while sentinels_received < 2:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        if item is None:
            sentinels_received += 1
            continue

        yield item
        lines_emitted += 1
        if lines_emitted >= MAX_OUTPUT_LINES:
            yield {"type": "system", "data": f"⚠ Output capped at {MAX_OUTPUT_LINES} lines.", "pid": pid}
            proc.kill()
            break

    await asyncio.gather(*tasks, return_exceptions=True)
    await proc.wait()

    _running.pop(pid, None)
    if script_path and script_path.exists():
        script_path.unlink(missing_ok=True)

    rc = proc.returncode if proc.returncode is not None else -1
    icon = "✅" if rc == 0 else "❌"
    yield {"type": "exit", "data": f"{icon} Process exited (code {rc})", "pid": pid, "code": rc}


def _build_command(
    code: str,
    language: str,
    filename: str,
) -> tuple[list[str] | None, Path | None]:
    """Write code to a temp file and return the command to run it.

    Returns:
        (cmd_list, script_path) or (None, None) if language unsupported.
    """
    if language == "python":
        path = _SANDBOX_DIR / f"{filename}.py"
        path.write_text(code, encoding="utf-8")
        return [sys.executable, "-u", str(path)], path

    if language in ("javascript", "typescript"):
        node = shutil.which("node")
        if not node:
            return None, None
        path = _SANDBOX_DIR / f"{filename}.js"
        path.write_text(code, encoding="utf-8")
        return [node, str(path)], path

    if language == "bash":
        path = _SANDBOX_DIR / f"{filename}.sh"
        path.write_text(code, encoding="utf-8")
        return ["/bin/bash", str(path)], path

    if language == "rust":
        # Compile then run — only if rustc present
        rustc = shutil.which("rustc")
        if not rustc:
            return None, None
        src = _SANDBOX_DIR / f"{filename}.rs"
        out = _SANDBOX_DIR / filename
        src.write_text(code, encoding="utf-8")
        # Compile first (blocking is fine — we'll surface compile errors)
        return [rustc, str(src), "-o", str(out), "&&", str(out)], src

    return None, None
