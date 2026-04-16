"""Provider registry — discovers, instantiates, and health-checks all providers."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from ag.providers.base import BaseProvider, ProviderHealth
from ag.providers.ollama import OllamaProvider
from ag.providers.openai_provider import OpenAIProvider, DeepSeekProvider
from ag.providers.anthropic_provider import AnthropicProvider
from ag.providers.gemini_provider import GeminiProvider
from ag.providers.compat_providers import (
    MistralProvider,
    GroqProvider,
    CohereProvider,
    TogetherProvider,
)


# Map config key → provider class
_PROVIDER_MAP: dict[str, type] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "mistral": MistralProvider,
    "groq": GroqProvider,
    "cohere": CohereProvider,
    "together": TogetherProvider,
    "deepseek": DeepSeekProvider,
}


def _expand_env(value: str) -> str:
    """Expand ${VAR} env var placeholders in a string value."""
    return os.path.expandvars(value) if isinstance(value, str) else value


def _expand_config(config: dict) -> dict:
    """Recursively expand env vars in a config dict."""
    return {
        k: _expand_config(v) if isinstance(v, dict) else _expand_env(v)
        for k, v in config.items()
    }


class ProviderRegistry:
    """Manages all configured LLM providers and their health state."""

    def __init__(self, providers_config: dict) -> None:
        """Instantiate all enabled providers from the config section."""
        self._providers: dict[str, BaseProvider] = {}
        self._health: dict[str, ProviderHealth] = {}

        for key, cls in _PROVIDER_MAP.items():
            section = providers_config.get(key, {})
            if not section.get("enabled", True):
                continue
            expanded = _expand_config(section)
            self._providers[key] = cls(expanded)

    def get(self, name: str) -> Optional[BaseProvider]:
        """Return a provider by name, or None if not registered."""
        return self._providers.get(name)

    def all(self) -> dict[str, BaseProvider]:
        """Return all registered providers."""
        return dict(self._providers)

    async def check_all(self) -> dict[str, ProviderHealth]:
        """Run health checks on all providers concurrently."""
        tasks = {
            name: asyncio.create_task(p.health_check())
            for name, p in self._providers.items()
        }
        results: dict[str, ProviderHealth] = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as exc:
                from ag.providers.base import ProviderHealth
                results[name] = ProviderHealth(
                    name=name, available=False, error=str(exc)
                )
        self._health = results
        return results

    def last_health(self) -> dict[str, ProviderHealth]:
        """Return the most recently fetched health snapshot."""
        return dict(self._health)

    def available_providers(self) -> list[str]:
        """Return names of providers whose last health check passed."""
        return [name for name, h in self._health.items() if h.available]
