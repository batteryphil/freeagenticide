"""File operations tool — read, write, list, and grep files."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from ag.tools.base import BaseTool, ToolResult


class FileOpsTool(BaseTool):
    """Read, write, list, and grep local files."""

    def __init__(self, config: dict) -> None:
        """Initialise FileOpsTool with config."""
        super().__init__("file_ops", config)
        self.max_kb: int = config.get("max_file_size_kb", 512)

    async def run(
        self,
        operation: str,
        path: str,
        content: Optional[str] = None,
        pattern: Optional[str] = None,
        **_: Any,
    ) -> ToolResult:
        """Dispatch to read / write / list / grep operations.

        Args:
            operation: One of ``read``, ``write``, ``list``, ``grep``.
            path: File or directory path.
            content: Content to write (write operation only).
            pattern: Regex pattern to search for (grep operation only).
        """
        ops = {
            "read": self._read,
            "write": self._write,
            "list": self._list,
            "grep": self._grep,
        }
        handler = ops.get(operation)
        if not handler:
            return ToolResult(
                tool=self.name,
                success=False,
                output="",
                error=f"Unknown operation '{operation}'. Choose: {list(ops)}",
            )
        return await handler(path=path, content=content, pattern=pattern)

    async def _read(self, path: str, **_: Any) -> ToolResult:
        """Read a text file and return its contents."""
        try:
            p = Path(path).expanduser()
            if not p.exists():
                return ToolResult(tool=self.name, success=False, output="", error=f"File not found: {path}")
            size_kb = p.stat().st_size / 1024
            if size_kb > self.max_kb:
                return ToolResult(
                    tool=self.name, success=False, output="",
                    error=f"File too large ({size_kb:.1f} KB > {self.max_kb} KB limit)",
                )
            text = p.read_text(errors="replace")
            return ToolResult(tool=self.name, success=True, output=text, metadata={"path": str(p), "size_kb": size_kb})
        except Exception as exc:
            return ToolResult(tool=self.name, success=False, output="", error=str(exc))

    async def _write(self, path: str, content: Optional[str] = None, **_: Any) -> ToolResult:
        """Write *content* to *path*, creating parent directories as needed."""
        if content is None:
            return ToolResult(tool=self.name, success=False, output="", error="content is required for write")
        try:
            p = Path(path).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return ToolResult(tool=self.name, success=True, output=f"Wrote {len(content)} chars to {path}")
        except Exception as exc:
            return ToolResult(tool=self.name, success=False, output="", error=str(exc))

    async def _list(self, path: str, **_: Any) -> ToolResult:
        """List directory contents."""
        try:
            p = Path(path).expanduser()
            if not p.is_dir():
                return ToolResult(tool=self.name, success=False, output="", error=f"Not a directory: {path}")
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            lines = [
                f"{'📁' if e.is_dir() else '📄'} {e.name}" + (f"  ({e.stat().st_size} B)" if e.is_file() else "")
                for e in entries
            ]
            return ToolResult(tool=self.name, success=True, output="\n".join(lines) or "(empty)")
        except Exception as exc:
            return ToolResult(tool=self.name, success=False, output="", error=str(exc))

    async def _grep(self, path: str, pattern: Optional[str] = None, **_: Any) -> ToolResult:
        """Search for *pattern* in all text files under *path*."""
        if not pattern:
            return ToolResult(tool=self.name, success=False, output="", error="pattern is required for grep")
        try:
            compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            p = Path(path).expanduser()
            files = [p] if p.is_file() else list(p.rglob("*"))
            matches: list[str] = []
            for f in files:
                if not f.is_file():
                    continue
                if f.stat().st_size / 1024 > self.max_kb:
                    continue
                try:
                    text = f.read_text(errors="replace")
                    for i, line in enumerate(text.splitlines(), 1):
                        if compiled.search(line):
                            matches.append(f"{f}:{i}:  {line.strip()}")
                except Exception:
                    continue
            if not matches:
                return ToolResult(tool=self.name, success=True, output="No matches found.")
            return ToolResult(tool=self.name, success=True, output="\n".join(matches[:100]))
        except Exception as exc:
            return ToolResult(tool=self.name, success=False, output="", error=str(exc))

    def describe(self) -> dict:
        """Return OpenAI function schema for this tool."""
        return {
            "type": "function",
            "function": {
                "name": "file_ops",
                "description": "Read, write, list, or grep files on the local filesystem.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string", "enum": ["read", "write", "list", "grep"]},
                        "path": {"type": "string", "description": "File or directory path."},
                        "content": {"type": "string", "description": "Content to write (write only)."},
                        "pattern": {"type": "string", "description": "Regex search pattern (grep only)."},
                    },
                    "required": ["operation", "path"],
                },
            },
        }
