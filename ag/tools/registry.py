"""Tool registry — instantiates and exposes all enabled tools."""

from __future__ import annotations

from typing import Optional

from ag.tools.base import BaseTool, ToolResult
from ag.tools.shell import ShellTool
from ag.tools.file_ops import FileOpsTool
from ag.tools.web_search import WebSearchTool
from ag.tools.code_exec import CodeExecTool


class ToolRegistry:
    """Holds all configured tools and dispatches calls by name."""

    def __init__(self, tools_config: dict) -> None:
        """Instantiate enabled tools from config."""
        self._tools: dict[str, BaseTool] = {}

        tool_map: dict[str, type] = {
            "shell": ShellTool,
            "file_ops": FileOpsTool,
            "web_search": WebSearchTool,
            "code_exec": CodeExecTool,
        }
        for key, cls in tool_map.items():
            cfg = tools_config.get(key, {})
            if cfg.get("enabled", True):
                self._tools[key] = cls(cfg)

    def get(self, name: str) -> Optional[BaseTool]:
        """Return a tool by name, or None if not registered."""
        return self._tools.get(name)

    def all(self) -> dict[str, BaseTool]:
        """Return all enabled tools."""
        return dict(self._tools)

    def schemas(self) -> list[dict]:
        """Return OpenAI-style function schemas for all enabled tools."""
        return [t.describe() for t in self._tools.values()]

    async def run(self, tool_name: str, **kwargs) -> ToolResult:
        """Find and execute a tool by name."""
        tool = self.get(tool_name)
        if tool is None:
            return ToolResult(
                tool=tool_name,
                success=False,
                output="",
                error=f"Unknown tool: '{tool_name}'",
            )
        return await tool.run(**kwargs)
