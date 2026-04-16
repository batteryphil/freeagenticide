"""Shared state and types across the entire agent tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ag.providers.registry import ProviderRegistry
    from ag.core.router import Router
    from ag.tools.registry import ToolRegistry


@dataclass
class AgentChunk:
    """A streaming chunk from any agent in the tree."""
    text: str
    agent_name: str
    depth: int
    is_tool_call: bool = False
    is_tool_result: bool = False
    is_final: bool = False


@dataclass
class AgentContext:
    """Single shared instance across the entire agent tree for a session."""
    session_id: str
    registry: ProviderRegistry
    router: Router
    tools: ToolRegistry

    # Globally accumulated — mutated in-place by any agent
    total_cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0

    # Stream callback — identity-aware for UI routing
    output_callback: Callable[[AgentChunk], None] | None = None
