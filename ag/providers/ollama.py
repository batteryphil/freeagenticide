"""Ollama provider — routes to local Ollama or any llama.cpp/vLLM server."""

from __future__ import annotations

import time
from typing import AsyncIterator, Optional

import httpx

from ag.providers.base import (
    BaseProvider,
    CompletionChunk,
    CompletionRequest,
    ProviderHealth,
)


class OllamaProvider(BaseProvider):
    """Provider for Ollama (and OpenAI-compatible local servers)."""

    _PRICE_PER_TOKEN = 0.0  # local = free

    def __init__(self, config: dict) -> None:
        """Initialise with config dict containing base_url."""
        super().__init__("ollama", config)
        self._is_local = True
        self.base_url: str = config.get("base_url", "http://localhost:11434").rstrip("/")
        self.timeout: int = config.get("timeout", 120)
        # Seed from config so list_models() works before the first health check.
        default = config.get("default_model", "llama3.2:3b")
        self._cached_models: list[str] = [default] if default else []

    async def complete(
        self, request: CompletionRequest
    ) -> AsyncIterator[CompletionChunk]:
        """Stream tokens from Ollama chat API."""
        model = request.model or self.config.get("default_model", "llama3.2:3b")
        payload = {
            "model": model,
            "messages": request.messages,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    import json
                    data = json.loads(line)
                    done = data.get("done", False)
                    text = data.get("message", {}).get("content", "")
                    if done:
                        eval_count = data.get("eval_count", 0)
                        prompt_eval_count = data.get("prompt_eval_count", 0)
                        yield CompletionChunk(
                            text="",
                            provider=self.name,
                            model=model,
                            is_final=True,
                            tokens_in=prompt_eval_count,
                            tokens_out=eval_count,
                            cost_usd=0.0,
                            latency_ms=self._elapsed_ms(t0),
                        )
                    else:
                        yield CompletionChunk(
                            text=text,
                            provider=self.name,
                            model=model,
                            latency_ms=self._elapsed_ms(t0),
                        )

    async def health_check(self) -> ProviderHealth:
        """Ping Ollama and fetch available models."""
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                self._cached_models = models
                return ProviderHealth(
                    name=self.name,
                    available=True,
                    latency_ms=self._elapsed_ms(t0),
                    models=models,
                )
        except Exception as exc:
            return ProviderHealth(
                name=self.name,
                available=False,
                error=str(exc),
            )

    def list_models(self) -> list[str]:
        """Return cached model list (populated after health_check)."""
        return self._cached_models
