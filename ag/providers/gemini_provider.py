"""Google Gemini provider using the google-genai SDK (2026)."""


from __future__ import annotations

import time
from typing import AsyncIterator

from ag.providers.base import (
    BaseProvider,
    CompletionChunk,
    CompletionRequest,
    ProviderHealth,
)

# USD per 1M tokens
_COST_TABLE: dict[str, tuple[float, float]] = {
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-1.5-pro": (3.50, 10.50),
    "gemini-1.5-flash": (0.075, 0.30),
}

_DEFAULT_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


class GeminiProvider(BaseProvider):
    """Provider for Google Gemini models."""

    def __init__(self, config: dict) -> None:
        """Initialise with config dict containing api_key."""
        super().__init__("gemini", config)
        self._is_local = False

    def _build_client(self):
        """Return a configured google.genai Client instance."""
        from google import genai  # noqa: PLC0415

        return genai.Client(api_key=self.config.get("api_key", ""))

    def get_cost(self, tokens_in: int, tokens_out: int, model: str) -> float:
        """Calculate USD cost from Gemini pricing table."""
        prices = _COST_TABLE.get(model, (1.25, 5.00))
        return (tokens_in * prices[0] + tokens_out * prices[1]) / 1_000_000

    async def complete(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionChunk]:
        """Stream Gemini completion chunks via google.genai SDK."""
        model_name = request.model or self.config.get("default_model", "gemini-2.0-flash")
        client = self._build_client()
        t0 = time.monotonic()

        # Build contents list from messages
        from google.genai import types as genai_types  # noqa: PLC0415

        contents = []
        for msg in request.messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(
                genai_types.Content(
                    role=role,
                    parts=[genai_types.Part.from_text(text=msg["content"])],
                )
            )

        # Inject system prompt as a system instruction
        config_kwargs: dict = {}
        if request.system:
            config_kwargs["system_instruction"] = request.system
        if request.temperature is not None:
            config_kwargs["temperature"] = request.temperature

        gen_config = genai_types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

        tokens_in = tokens_out = 0
        async for chunk in await client.aio.models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=gen_config,
        ):
            if chunk.text:
                yield CompletionChunk(
                    text=chunk.text,
                    provider=self.name,
                    model=model_name,
                    latency_ms=self._elapsed_ms(t0),
                )
            if chunk.usage_metadata:
                tokens_in = chunk.usage_metadata.prompt_token_count or 0
                tokens_out = chunk.usage_metadata.candidates_token_count or 0

        yield CompletionChunk(
            text="",
            provider=self.name,
            model=model_name,
            is_final=True,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=self.get_cost(tokens_in, tokens_out, model_name),
            latency_ms=self._elapsed_ms(t0),
        )

    async def health_check(self) -> ProviderHealth:
        """Verify Gemini API key by listing models."""
        t0 = time.monotonic()
        if not self.config.get("api_key"):
            return ProviderHealth(
                name=self.name, available=False, error="No API key configured"
            )
        try:
            from google import genai  # noqa: PLC0415

            client = genai.Client(api_key=self.config.get("api_key", ""))
            model_page = client.models.list()
            models = [
                m.name.replace("models/", "")
                for m in model_page
                if hasattr(m, "supported_actions")
                   and "generateContent" in (m.supported_actions or [])
            ] or _DEFAULT_MODELS
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
        """Return known Gemini model list."""
        return _DEFAULT_MODELS
