"""OpenAI provider (also handles Azure OpenAI and DeepSeek-compatible endpoints)."""

from __future__ import annotations

import time
from typing import AsyncIterator, Optional

from ag.providers.base import (
    BaseProvider,
    CompletionChunk,
    CompletionRequest,
    ProviderHealth,
)

# Cost table (USD per 1M tokens) — input / output
_COST_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o": (5.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o3-mini": (1.10, 4.40),
    "deepseek-chat": (0.14, 0.28),
    "deepseek-reasoner": (0.55, 2.19),
}

_DEFAULT_MODELS = [
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini", "o3-mini",
]


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI (and OpenAI-compatible) APIs."""

    def __init__(self, config: dict, name: str = "openai") -> None:
        """Initialise with config dict containing api_key."""
        super().__init__(name, config)
        self._is_local = False

    def _build_client(self):
        """Build and return an AsyncOpenAI client from config."""
        from openai import AsyncOpenAI

        kwargs: dict = {"api_key": self.config.get("api_key", "")}
        if base_url := self.config.get("base_url"):
            kwargs["base_url"] = base_url
        if api_version := self.config.get("api_version"):
            # Azure uses httpx default headers
            kwargs["default_headers"] = {"api-version": api_version}
        return AsyncOpenAI(**kwargs)

    def get_cost(self, tokens_in: int, tokens_out: int, model: str) -> float:
        """Calculate USD cost based on model pricing table."""
        prices = _COST_TABLE.get(model, (1.0, 3.0))
        return (tokens_in * prices[0] + tokens_out * prices[1]) / 1_000_000

    async def complete(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionChunk]:
        """Stream completion chunks using the OpenAI streaming API."""
        client = self._build_client()
        model = request.model or self.config.get("default_model", "gpt-4o-mini")
        messages = list(request.messages)
        if request.system:
            messages = [{"role": "system", "content": request.system}] + messages

        t0 = time.monotonic()
        tokens_in = tokens_out = 0

        async with client.chat.completions.stream(
            model=model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ) as stream:
            async for event in stream:
                choice = event.choices[0] if event.choices else None
                if choice is None:
                    continue
                delta_text = (choice.delta.content or "") if choice.delta else ""
                if delta_text:
                    tokens_out += 1
                    yield CompletionChunk(
                        text=delta_text,
                        provider=self.name,
                        model=model,
                        latency_ms=self._elapsed_ms(t0),
                    )
            # Final accounting
            final = await stream.get_final_completion()
            if final.usage:
                tokens_in = final.usage.prompt_tokens
                tokens_out = final.usage.completion_tokens
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
        """Verify API key is set; optionally list available models."""
        t0 = time.monotonic()
        if not self.config.get("api_key"):
            return ProviderHealth(
                name=self.name, available=False, error="No API key configured"
            )
        try:
            client = self._build_client()
            page = await client.models.list()
            models = [m.id for m in page.data if "gpt" in m.id or "o1" in m.id or "o3" in m.id]
            return ProviderHealth(
                name=self.name,
                available=True,
                latency_ms=self._elapsed_ms(t0),
                models=models or _DEFAULT_MODELS,
            )
        except Exception as exc:
            return ProviderHealth(
                name=self.name, available=False, error=str(exc)
            )

    def list_models(self) -> list[str]:
        """Return default known model list."""
        return _DEFAULT_MODELS


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek via their OpenAI-compatible endpoint."""

    def __init__(self, config: dict) -> None:
        """Initialise DeepSeek as an OpenAI-compatible provider."""
        config.setdefault("base_url", "https://api.deepseek.com/v1")
        config.setdefault("default_model", "deepseek-chat")
        super().__init__(config, name="deepseek")

    def list_models(self) -> list[str]:
        """Return DeepSeek model list."""
        return ["deepseek-chat", "deepseek-reasoner"]
