"""UI-bridged tools — let the agent write code to the Monaco editor and run programs.

These tools are special because they have a side effect beyond returning a string:
they push messages to the connected WebSocket so the UI reacts in real time.

  write_to_editor  →  pushes {type:"editor_update", code, language} to WS
                       Monaco updates instantly; agent gets confirmation back

  run_in_ui        →  runs code via the subprocess runner, streams output to the
                       terminal panel, returns the full stdout+stderr to the agent
                       so it can inspect results and decide what to do next

Both tools receive a ``ws_send`` coroutine injected by WSSession at construction.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Coroutine

from ag.tools.base import BaseTool, ToolResult
from ag.server.runner import run_code

# Output returned to the agent is cap capped to avoid flooding the context.
_MAX_AGENT_OUTPUT = 8_000


class WriteToEditorTool(BaseTool):
    """Write code to the Monaco editor pane in the UI.

    The agent calls this to 'show its work' — the editor updates live
    so the user can see exactly what is being built.
    """

    def __init__(self, ws_send: Callable, config: dict | None = None) -> None:
        """Initialise with a WebSocket send callback.

        Args:
            ws_send: Coroutine callable that accepts a dict and sends it
                     as JSON to the connected WebSocket client.
            config: Optional config dict (unused but keeps interface consistent).
        """
        super().__init__("write_to_editor", config or {})
        self._ws_send = ws_send

    async def run(self, code: str = "", language: str = "python", **_: Any) -> ToolResult:
        """Write code + language to the Monaco editor.

        Args:
            code: The full source code to put in the editor.
            language: Monaco language identifier (python, javascript, html, bash, …).

        Returns:
            ToolResult confirming the editor was updated.
        """
        language = language.lower().strip() or "python"
        try:
            await self._ws_send({
                "type": "editor_update",
                "code": code,
                "language": language,
            })
            return ToolResult(
                tool="write_to_editor",
                success=True,
                output=f"Editor updated ({language}, {len(code)} chars). "
                       "User can see the code in the Monaco pane.",
            )
        except Exception as exc:
            return ToolResult(
                tool="write_to_editor",
                success=False,
                output="",
                error=f"Failed to send editor update: {exc}",
            )

    def describe(self) -> dict:
        """OpenAI-style function schema for write_to_editor."""
        return {
            "name": "write_to_editor",
            "description": (
                "Write source code to the Monaco code editor pane visible in the UI. "
                "Use this whenever you write code — the user sees it appear live. "
                "After writing, call run_in_ui to execute it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The complete source code to write.",
                    },
                    "language": {
                        "type": "string",
                        "description": (
                            "Language for syntax highlighting. "
                            "One of: python, javascript, typescript, bash, html, rust."
                        ),
                        "default": "python",
                    },
                },
                "required": ["code"],
            },
        }


class RunInUITool(BaseTool):
    """Execute code and stream output to the terminal panel.

    The agent can use this to build and run programs autonomously:
    1. Write code with write_to_editor
    2. Run it with run_in_ui
    3. Read the output and fix bugs
    4. Repeat until it works

    For HTML/JS programs the browser iframe opens automatically.
    For Python GUI programs (Pygame, Tkinter) the window opens on the desktop.
    """

    def __init__(self, ws_send: Callable, config: dict | None = None) -> None:
        """Initialise with a WebSocket send callback.

        Args:
            ws_send: Coroutine callable to push messages to the WS client.
            config: Optional config dict.
        """
        super().__init__("run_in_ui", config or {})
        self._ws_send = ws_send

    async def run(
        self,
        code: str = "",
        language: str = "python",
        filename: str = "main",
        **_: Any,
    ) -> ToolResult:
        """Run code and stream output to the terminal panel.

        Both stdout and stderr are streamed live to the UI terminal.
        The full output is also returned to the agent for inspection.

        Args:
            code: Source code to execute.
            language: Execution language (python, javascript, bash, html).
            filename: Base name for the temp file (no extension).

        Returns:
            ToolResult with combined stdout + stderr (capped at 8k chars).
        """
        language = language.lower().strip() or "python"

        # Signal UI to open / clear the terminal panel
        await self._ws_send({
            "type": "terminal_start",
            "language": language,
            "filename": filename,
        })

        output_lines: list[str] = []
        exit_code: int = 0
        html_url: str | None = None
        chars = 0

        async for event in run_code(code, language, filename):
            # Forward every event to the UI terminal in real time
            try:
                await self._ws_send({"type": "terminal_event", "event": event})
            except Exception:
                pass  # Client disconnected during run

            etype = event.get("type", "")
            data = event.get("data", "")

            if etype in ("stdout", "stderr", "system"):
                line = f"[{etype}] {data}" if etype != "stdout" else data
                output_lines.append(line)
                chars += len(line)

            elif etype == "exit":
                exit_code = event.get("code", 0)
                output_lines.append(data)

            elif etype == "stream_end":
                break

            # Check for HTML URL
            if event.get("url"):
                html_url = event["url"]
                output_lines.append(f"[html] Served at {html_url}")

            # Cap output sent back to agent
            if chars > _MAX_AGENT_OUTPUT:
                output_lines.append(
                    f"[truncated — {chars} chars, showing first {_MAX_AGENT_OUTPUT}]"
                )
                break

        combined = "\n".join(output_lines)
        success = exit_code == 0 or html_url is not None

        return ToolResult(
            tool="run_in_ui",
            success=success,
            output=combined[:_MAX_AGENT_OUTPUT],
            error=None if success else f"Process exited with code {exit_code}",
            metadata={"exit_code": exit_code, "html_url": html_url},
        )

    def describe(self) -> dict:
        """OpenAI-style function schema for run_in_ui."""
        return {
            "name": "run_in_ui",
            "description": (
                "Execute code and stream the output to the terminal panel in the UI. "
                "The user sees live stdout + stderr. Returns full output so you can "
                "inspect results, fix bugs, and iterate. "
                "For Python GUI programs (Pygame, Tkinter) the window opens on the user's desktop. "
                "For HTML programs an iframe opens in the UI. "
                "Always call write_to_editor first so the user can see the code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Source code to execute.",
                    },
                    "language": {
                        "type": "string",
                        "description": "One of: python, javascript, bash, html.",
                        "default": "python",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Base filename (no extension) for the temp file.",
                        "default": "main",
                    },
                },
                "required": ["code"],
            },
        }
