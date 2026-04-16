"""Pydantic models for WebSocket message protocol.

Upstream (server → client):
  ChunkMessage   — streamed token from an AgentChunk
  StatusMessage  — provider health + session cost snapshot
  ErrorMessage   — agent or tool error
  DoneMessage    — final signal for a response turn

Downstream (client → server):
  ChatMessage    — user sends a message
  InterruptMessage — user requests stream cancellation
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel


# ── Server → Client ───────────────────────────────────────────────────────────

class ChunkMessage(BaseModel):
    """A single streamed token or tool annotation from the agent."""

    type: Literal["chunk"] = "chunk"
    text: str
    agent_name: str = "assistant"
    depth: int = 0
    is_tool_call: bool = False
    is_tool_result: bool = False
    is_final: bool = False


class ProviderInfo(BaseModel):
    """Status of a single provider."""

    name: str
    available: bool
    model: Optional[str] = None
    latency_ms: Optional[float] = None


class StatusMessage(BaseModel):
    """Periodic status snapshot sent after each response turn."""

    type: Literal["status"] = "status"
    providers: list[ProviderInfo] = []
    total_cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    active_model: str = ""
    active_provider: str = ""


class ErrorMessage(BaseModel):
    """Agent or WebSocket error."""

    type: Literal["error"] = "error"
    message: str
    recoverable: bool = True


class DoneMessage(BaseModel):
    """Signals end of a single response turn."""

    type: Literal["done"] = "done"
    total_cost_usd: float = 0.0


# ── Client → Server ───────────────────────────────────────────────────────────

class IncomingChat(BaseModel):
    """User chat message."""

    type: Literal["chat"]
    message: str


class IncomingInterrupt(BaseModel):
    """Request to cancel the current stream."""

    type: Literal["interrupt"]


# ── Model management request bodies ──────────────────────────────────────────

class ActivateBody(BaseModel):
    """Request body for POST /api/models/activate."""

    model_id: str
    provider: str = "ollama"


class PullBody(BaseModel):
    """Request body for POST /api/models/pull."""

    model_id: str
