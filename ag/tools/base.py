"""Abstract base class and result type for all Antigravity tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolResult:
    """Standardised result returned by any tool."""

    tool: str
    success: bool
    output: str
    error: Optional[str] = None
    metadata: Optional[dict] = None


class BaseTool(ABC):
    """Abstract tool. All tools must implement this interface."""

    def __init__(self, name: str, config: dict) -> None:
        """Initialise the tool with its config section."""
        self.name = name
        self.config = config
        self.enabled: bool = config.get("enabled", True)

    @abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given keyword arguments."""
        ...

    @abstractmethod
    def describe(self) -> dict:
        """Return an OpenAI-style function schema describing this tool."""
        ...
