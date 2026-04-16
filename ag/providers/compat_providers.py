"""Mistral, Groq, Cohere, and Together.ai providers — all OpenAI-compatible."""

from __future__ import annotations

import time
from typing import AsyncIterator

from ag.providers.base import (
    BaseProvider,
    CompletionChunk,
    CompletionRequest,
    ProviderHealth,
)


class _OpenAICompatProvider(BaseProvider):
    """Shared base for OpenAI-compatible providers (Mistral, Groq, etc.)."""

    BASE_URL: str = ""
    DEFAULT_MODEL: str = ""
    MODELS: list[str] = []
    COST_TABLE: dict[str, tuple[float, float]] = {}

    def __init__(self, name: str, config: dict) -> None:
        """Initialise with provider name and config."""
        super().__init__(name, config)
        self._is_local = False

    def _build_client(self):
        """Build an AsyncOpenAI client pointed at this provider's base URL."""
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            api_key=self.config.get("api_key", "placeholder"),
            base_url=self.config.get("base_url", self.BASE_URL),
        )

    def get_cost(self, tokens_in: int, tokens_out: int, model: str) -> float:
        """Calculate USD cost from provider cost table."""
        prices = self.COST_TABLE.get(model, (0.50, 1.50))
        return (tokens_in * prices[0] + tokens_out * prices[1]) / 1_000_000

    async def complete(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionChunk]:
        """Stream tokens via OpenAI-compatible chat completions endpoint."""
        client = self._build_client()
        model = request.model or self.config.get("default_model", self.DEFAULT_MODEL)
        messages = list(request.messages)
        if request.system:
            messages = [{"role": "system", "content": request.system}] + messages

        t0 = time.monotonic()
        tokens_in = tokens_out = 0

        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.usage:
                tokens_in = chunk.usage.prompt_tokens
                tokens_out = chunk.usage.completion_tokens
            choice = chunk.choices[0] if chunk.choices else None
            if choice and choice.delta and choice.delta.content:
                yield CompletionChunk(
                    text=choice.delta.content,
                    provider=self.name,
                    model=model,
                    latency_ms=self._elapsed_ms(t0),
                )

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
        """Check that an API key is present and can list models."""
        t0 = time.monotonic()
        if not self.config.get("api_key"):
            return ProviderHealth(
                name=self.name, available=False, error="No API key configured"
            )
        try:
            client = self._build_client()
            resp = await client.models.list()
            models = [m.id for m in resp.data] or self.MODELS
            return ProviderHealth(
                name=self.name,
                available=True,
                latency_ms=self._elapsed_ms(t0),
                models=models,
            )
        except Exception as exc:
            return ProviderHealth(
                name=self.name, available=False, error=str(exc)
            )

    def list_models(self) -> list[str]:
        """Return static known model list."""
        return self.MODELS


# ─────────────────────────────────────────────────────────────────────────────
# Concrete Providers
# ─────────────────────────────────────────────────────────────────────────────

class MistralProvider(_OpenAICompatProvider):
    """Mistral AI provider."""

    BASE_URL = "https://api.mistral.ai/v1"
    DEFAULT_MODEL = "mistral-small-latest"
    MODELS = ["mistral-small-latest", "mistral-medium-latest", "mistral-large-latest", "codestral-latest"]
    COST_TABLE = {
        "mistral-small-latest": (0.10, 0.30),
        "mistral-medium-latest": (2.70, 8.10),
        "mistral-large-latest": (2.00, 6.00),
        "codestral-latest": (0.20, 0.60),
    }

    def __init__(self, config: dict) -> None:
        """Initialise Mistral provider."""
        super().__init__("mistral", config)


class GroqProvider(_OpenAICompatProvider):
    """Groq provider — ultra-fast inference."""

    BASE_URL = "https://api.groq.com/openai/v1"
    DEFAULT_MODEL = "llama3-8b-8192"
    MODELS = [
        "llama3-8b-8192", "llama3-70b-8192", "llama-3.1-8b-instant",
        "mixtral-8x7b-32768", "gemma2-9b-it",
    ]
    COST_TABLE = {
        "llama3-8b-8192": (0.05, 0.08),
        "llama3-70b-8192": (0.59, 0.79),
        "mixtral-8x7b-32768": (0.24, 0.24),
    }

    def __init__(self, config: dict) -> None:
        """Initialise Groq provider."""
        super().__init__("groq", config)


class CohereProvider(_OpenAICompatProvider):
    """Cohere provider via compatibility endpoint."""

    BASE_URL = "https://api.cohere.com/compatibility/v1"
    DEFAULT_MODEL = "command-r-plus"
    MODELS = ["command-r", "command-r-plus", "command-r7b-12-2024"]
    COST_TABLE = {
        "command-r": (0.15, 0.60),
        "command-r-plus": (2.50, 10.00),
    }

    def __init__(self, config: dict) -> None:
        """Initialise Cohere provider."""
        super().__init__("cohere", config)


class TogetherProvider(_OpenAICompatProvider):
    """Together.ai provider."""

    BASE_URL = "https://api.together.xyz/v1"
    DEFAULT_MODEL = "meta-llama/Llama-3-70b-chat-hf"
    MODELS = [
        "meta-llama/Llama-3-70b-chat-hf",
        "meta-llama/Llama-3-8b-chat-hf",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "Qwen/Qwen2.5-72B-Instruct-Turbo",
    ]
    COST_TABLE = {
        "meta-llama/Llama-3-70b-chat-hf": (0.88, 0.88),
        "meta-llama/Llama-3-8b-chat-hf": (0.18, 0.18),
    }

    def __init__(self, config: dict) -> None:
        """Initialise Together.ai provider."""
        super().__init__("together", config)
