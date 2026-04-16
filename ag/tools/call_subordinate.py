"""call_subordinate tool — exposes the agent spawn mechanism as a named tool.

Note: When running inside an Agent instance, _call_subordinate is handled
natively by Agent._dispatch_tool(). This module provides:
  1. An OpenAI-style JSON schema (describe()) so the function schema
     can be injected into system prompts.
  2. A standalone version for any non-Agent caller (e.g. tests, scripts).
"""

from __future__ import annotations

from typing import Any

from ag.tools.base import BaseTool, ToolResult


_SCHEMA: dict = {
    "name": "call_subordinate",
    "description": (
        "Delegate a task to a specialised sub-agent. "
        "Use when the current task would benefit from a specific expertise "
        "(developer, researcher, coder). "
        "The sub-agent runs to completion and returns its full response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": (
                    "The complete task description for the sub-agent. "
                    "Be explicit — the sub-agent cannot see the parent conversation "
                    "unless reset=false."
                ),
            },
            "agent_profile": {
                "type": "string",
                "enum": ["default", "developer", "researcher", "coder"],
                "description": "Which specialised agent profile to use.",
            },
            "reset": {
                "type": "boolean",
                "description": (
                    "If true (default), the sub-agent starts with a fresh session. "
                    "If false, it inherits the last 6 messages of the parent's history."
                ),
            },
            "context_msgs": {
                "type": "integer",
                "description": (
                    "Number of recent parent messages to seed when reset=false. "
                    "Ignored when reset=true. Default: 6."
                ),
            },
        },
        "required": ["message"],
    },
}


class CallSubordinateTool(BaseTool):
    """Standalone tool wrapper — used by non-Agent callers.

    Inside an Agent message loop, call_subordinate is handled natively
    (see Agent._dispatch_tool) so the agent has access to its own context.
    This class provides the describe() schema and a stub run() for registry
    compatibility.
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialise with optional config dict."""
        super().__init__("call_subordinate", config or {})

    def describe(self) -> dict:
        """Return the OpenAI-style function schema."""
        return _SCHEMA

    async def run(self, **kwargs: Any) -> ToolResult:
        """Stub: sub-agent spawning must go through Agent._dispatch_tool."""
        return ToolResult(
            tool=self.name,
            success=False,
            output="",
            error=(
                "call_subordinate must be invoked from within an Agent message "
                "loop. Use Agent._call_subordinate() directly."
            ),
        )
