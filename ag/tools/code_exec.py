"""Sandboxed Python code execution tool.

Security model (defence-in-depth):
  - Fresh interpreter per call — no shared state between executions.
  - ``-I`` (isolated) flag: ignores PYTHONPATH, site-packages interference.
  - ``-u`` flag: unbuffered output so partial output is captured on timeout.
  - Configurable timeout with guaranteed process teardown (SIGKILL on expiry).
  - Output capped at MAX_OUTPUT_CHARS to prevent context-window flooding.
  - working_dir defaults to /tmp/ag_sandbox (never the project root).

What it does *not* do (requires OS-level sandboxing for full isolation):
  - Does not block network access (use seccomp/nsjail for that).
  - Does not prevent filesystem writes outside working_dir.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import tempfile
import textwrap
from typing import Any

from ag.tools.base import BaseTool, ToolResult

# Hard cap on combined stdout+stderr returned to the session.
# Prevents a runaway print loop from consuming the context window.
_MAX_OUTPUT_CHARS = 4_000   # ~1 000 tokens


class CodeExecTool(BaseTool):
    """Execute Python code in an isolated subprocess sandbox."""

    def __init__(self, config: dict) -> None:
        """Initialise CodeExecTool with config.

        Config keys:
            timeout (int): Seconds before SIGKILL. Default 30.
            allow_network (bool): Informational only. Default False.
            working_dir (str): Execution cwd. Default /tmp/ag_sandbox.
            max_output_chars (int): Output cap. Default 4000.
        """
        super().__init__("code_exec", config)
        self.timeout: int = config.get("timeout", 30)
        self.allow_network: bool = config.get("allow_network", False)
        self.max_output_chars: int = config.get("max_output_chars", _MAX_OUTPUT_CHARS)
        raw_dir: str = config.get("working_dir", "/tmp/ag_sandbox")
        self._working_dir = raw_dir

    def _ensure_sandbox_dir(self) -> str:
        """Create the sandbox working directory if it doesn't exist."""
        os.makedirs(self._working_dir, exist_ok=True)
        return self._working_dir

    async def run(self, code: str, **_: Any) -> ToolResult:
        """Execute *code* in an isolated subprocess and capture stdout/stderr.

        Args:
            code: Python source code to run. Dedented automatically.

        Returns:
            ToolResult with combined output, or error on timeout/non-zero exit.
        """
        safe_code = textwrap.dedent(code).strip()
        if not safe_code:
            return ToolResult(
                tool=self.name, success=False, output="", error="Empty code block."
            )

        cwd = self._ensure_sandbox_dir()

        # -I: isolated mode (ignore PYTHONPATH, site customisation)
        # -u: unbuffered stdout/stderr (get partial output on timeout)
        cmd = [sys.executable, "-Iu", "-c", safe_code]

        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                # Prevent the child from inheriting sensitive env vars
                env=self._safe_env(),
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )

            out = stdout_bytes.decode(errors="replace").strip()
            err = stderr_bytes.decode(errors="replace").strip()
            rc = proc.returncode

            combined = self._format_output(out, err)

            if rc != 0:
                return ToolResult(
                    tool=self.name,
                    success=False,
                    output=combined,
                    error=err or f"Process exited with code {rc}",
                    metadata={"returncode": rc, "cwd": cwd},
                )
            return ToolResult(
                tool=self.name,
                success=True,
                output=combined or "(no output)",
                metadata={"returncode": 0, "cwd": cwd},
            )

        except asyncio.TimeoutError:
            # Guaranteed teardown — no zombie processes
            if proc is not None:
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass  # Already exited between check and kill
            return ToolResult(
                tool=self.name,
                success=False,
                output="",
                error=(
                    f"Execution timed out after {self.timeout}s. "
                    "Use smaller input data or split into multiple calls."
                ),
                metadata={"returncode": None, "timeout": True},
            )
        except Exception as exc:
            return ToolResult(
                tool=self.name, success=False, output="", error=str(exc)
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _safe_env(self) -> dict[str, str]:
        """Return a minimal environment for the subprocess.

        Strips PYTHONPATH / PYTHONSTARTUP to prevent env-level injection.
        Keeps PATH, HOME, TMPDIR so standard library functions work.
        """
        keep = {"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
        return {k: v for k, v in os.environ.items() if k in keep}

    def _format_output(self, stdout: str, stderr: str) -> str:
        """Combine stdout and stderr, cap at max_output_chars.

        Args:
            stdout: Decoded stdout string.
            stderr: Decoded stderr string.

        Returns:
            Combined output string, truncated with a notice if too long.
        """
        combined = stdout
        if stderr:
            combined += f"\n\n[stderr]\n{stderr}" if combined else f"[stderr]\n{stderr}"

        if len(combined) > self.max_output_chars:
            keep = self.max_output_chars - 80
            combined = (
                combined[:keep]
                + f"\n\n[Output truncated: {len(combined):,} chars. "
                f"Use narrower assertions or print only the relevant result.]"
            )
        return combined

    def describe(self) -> dict:
        """Return OpenAI-compatible function schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": "code_exec",
                "description": (
                    "Execute Python code in a subprocess and return stdout/stderr. "
                    "Use for calculations, data processing, testing logic, or "
                    "verifying code snippets. Output is capped at 4,000 chars."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": (
                                "Python source code to execute. "
                                "Print results explicitly — return values are not shown. "
                                "Example: print(2 + 2)"
                            ),
                        },
                    },
                    "required": ["code"],
                },
            },
        }
