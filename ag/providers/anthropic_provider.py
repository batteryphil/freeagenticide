"""Anthropic Claude provider with native streaming and extended thinking."""

from __future__ import annotations

import time
from typing import AsyncIterator

from ag.providers.base import (
    BaseProvider,
    CompletionChunk,
    CompletionRequest,
    ProviderHealth,
)

# USD per 1M tokens — (input, output)
_COST_TABLE: dict[str, tuple[float, float]] = {
    "claude-opus-4-5": (15.00, 75.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-3-5": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
}

_DEFAULT_MODELS = [
    "claude-haiku-3-5",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
]


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic Claude models."""

    def __init__(self, config: dict) -> None:
        """Initialise with config dict containing api_key."""
        super().__init__("anthropic", config)
        self._is_local = False

    def _build_client(self):
        """Build and return an AsyncAnthropic client."""
        import anthropic
        return anthropic.AsyncAnthropic(api_key=self.config.get("api_key", ""))

    def get_cost(self, tokens_in: int, tokens_out: int, model: str) -> float:
        """Calculate USD cost from Anthropic pricing table."""
        prices = _COST_TABLE.get(model, (3.00, 15.00))
        return (tokens_in * prices[0] + tokens_out * prices[1]) / 1_000_000

    async def complete(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionChunk]:
        """Stream Claude completion chunks."""
        client = self._build_client()
        model = request.model or self.config.get("default_model", "claude-haiku-3-5")
        t0 = time.monotonic()
        tokens_in = tokens_out = 0

        kwargs: dict = {
            "model": model,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.system:
            kwargs["system"] = request.system

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield CompletionChunk(
                    text=text,
                    provider=self.name,
                    model=model,
                    latency_ms=self._elapsed_ms(t0),
                )
            final = await stream.get_final_message()
            tokens_in = final.usage.input_tokens
            tokens_out = final.usage.output_tokens

        yield CompletionChunk(
            text="",
            provider=self.name,
            model=model,
            is_final=True,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=self.get_cost(tokens_in, tokens_out, model),
            latency_ms=self._elapsed_ms(t0),
        )

    async def health_check(self) -> ProviderHealth:
        """Verify API key by sending a minimal test message."""
        t0 = time.monotonic()
        if not self.config.get("api_key"):
            return ProviderHealth(
                name=self.name, available=False, error="No API key configured"
            )
        try:
            client = self._build_client()
            await client.messages.create(
                model="claude-haiku-3-5",
                max_tokens=1,
                messages=[{"role": "user", "content": "hi"}],
            )
            return ProviderHealth(
                name=self.name,
                available=True,
                latency_ms=self._elapsed_ms(t0),
                models=_DEFAULT_MODELS,
            )
        except Exception as exc:
            return ProviderHealth(
                name=self.name, available=False, error=str(exc)
            )

    def list_models(self) -> list[str]:
        """Return known Claude model list."""
        return _DEFAULT_MODELS
