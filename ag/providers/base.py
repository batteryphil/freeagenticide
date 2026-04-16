"""Abstract base class for all LLM providers."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class CompletionRequest:
    """Normalised request passed to any provider."""

    messages: list[dict]
    model: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096
    stream: bool = True
    system: Optional[str] = None


@dataclass
class CompletionChunk:
    """A single streamed token chunk returned by a provider."""

    text: str
    provider: str
    model: str
    is_final: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


@dataclass
class ProviderHealth:
    """Health snapshot for a provider."""

    name: str
    available: bool
    latency_ms: float = 0.0
    models: list[str] = field(default_factory=list)
    error: Optional[str] = None


class BaseProvider(ABC):
    """Abstract provider. All LLM backends must implement this interface."""

    def __init__(self, name: str, config: dict) -> None:
        """Initialise the provider with its config section."""
        self.name = name
        self.config = config
        self._is_local: bool = False

    @property
    def is_local(self) -> bool:
        """Return True if this provider runs locally (zero cost)."""
        return self._is_local

    @abstractmethod
    async def complete(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionChunk]:
        """Stream completion chunks for the given request."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Return a health snapshot for this provider."""
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return the models available through this provider."""
        ...

    def get_cost(self, tokens_in: int, tokens_out: int, model: str) -> float:
        """Calculate USD cost for a request. Override in cloud providers."""
        return 0.0

    def _elapsed_ms(self, start: float) -> float:
        """Helper: milliseconds since *start* (time.monotonic())."""
        return (time.monotonic() - start) * 1000
