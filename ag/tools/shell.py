"""Shell command execution tool with optional confirmation gate."""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from ag.tools.base import BaseTool, ToolResult


class ShellTool(BaseTool):
    """Executes shell commands in a subprocess."""

    def __init__(self, config: dict) -> None:
        """Initialise ShellTool with config."""
        super().__init__("shell", config)
        self.require_confirm: bool = config.get("require_confirm", True)
        self.timeout: int = config.get("timeout", 30)

    async def run(self, command: str, confirmed: bool = False, **_: Any) -> ToolResult:
        """Execute *command* in a subprocess and return its output.

        If ``require_confirm`` is True and ``confirmed`` is False, the tool
        returns a pending confirmation request instead of running.
        """
        if self.require_confirm and not confirmed:
            return ToolResult(
                tool=self.name,
                success=False,
                output="",
                error=f"CONFIRM_REQUIRED:{command}",
                metadata={"pending_command": command},
            )
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            out = stdout.decode(errors="replace")
            err = stderr.decode(errors="replace")
            if proc.returncode != 0:
                return ToolResult(
                    tool=self.name,
                    success=False,
                    output=out,
                    error=f"Exit {proc.returncode}: {err}",
                    metadata={"returncode": proc.returncode},
                )
            return ToolResult(
                tool=self.name,
                success=True,
                output=out or "(no output)",
                metadata={"returncode": 0},
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool=self.name,
                success=False,
                output="",
                error=f"Command timed out after {self.timeout}s",
            )
        except Exception as exc:
            return ToolResult(
                tool=self.name, success=False, output="", error=str(exc)
            )

    def describe(self) -> dict:
        """Return OpenAI function schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": "shell",
                "description": "Run a shell command and return its stdout/stderr.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The shell command to execute."},
                        "confirmed": {"type": "boolean", "description": "Set true to confirm execution."},
                    },
                    "required": ["command"],
                },
            },
        }
