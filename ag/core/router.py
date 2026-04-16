"""Smart router — scores prompt complexity and selects the best provider."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ag.providers.registry import ProviderRegistry


# Keywords that suggest reasoning / multi-step complexity
_COMPLEX_PATTERNS = [
    r"\b(explain|compare|analyze|analyse|design|refactor|optimize|optimise|debug|architecture)\b",
    r"\b(step[- ]by[- ]step|in detail|comprehensively|thoroughly)\b",
    r"\b(write a|implement|create|build|develop|generate)\b",
    r"\b(authentication|authorization|jwt|oauth|database|migration)\b",
    r"\b(full|complete|production|robust|scalable|enterprise)\b",
    r"\b(test|tests|testing|unit test|integration)\b",
    r"\b(algorithm|recursion|dynamic programming|machine learning)\b",
    r"```",          # code blocks in prompt
    r"(?s).{600,}",  # long prompts
]

_SIMPLE_PATTERNS = [
    r"^\s*(hi|hello|hey|thanks|thx|ok|sure|yes|no|bye)\s*[.!?]?\s*$",
    r"^\s*what (is|are) \w+\s*\??\s*$",
    r"^\s*(what time|who made|who built|what's your name)\b",
]

_COMPILED_COMPLEX = [re.compile(p, re.IGNORECASE) for p in _COMPLEX_PATTERNS]
_COMPILED_SIMPLE = [re.compile(p, re.IGNORECASE) for p in _SIMPLE_PATTERNS]


@dataclass
class RoutingDecision:
    """Result of the router's provider selection."""

    provider: str
    model: str
    reason: str
    complexity_score: float
    estimated_cost_usd: float


def _complexity_score(prompt: str) -> float:
    """Return a 0.0–1.0 score estimating prompt complexity.

    Higher means more likely to need a powerful cloud model.
    """
    score = 0.0
    text = prompt.strip()

    # Simple patterns lower score
    for pat in _COMPILED_SIMPLE:
        if pat.match(text):
            return 0.05

    # Complex patterns raise score additively (capped at 1.0)
    for pat in _COMPILED_COMPLEX:
        if pat.search(text):
            score += 0.15

    # Length heuristic: +0.1 per 200 chars over 400
    excess_chars = max(0, len(text) - 400)
    score += min(0.30, excess_chars / 2000)

    return min(1.0, score)


class Router:
    """Routes each request to the best available provider."""

    def __init__(self, config: dict, registry: ProviderRegistry) -> None:
        """Bind router to routing config and live provider registry."""
        self._cfg = config
        self._registry = registry
        self._session_cost: float = 0.0

    @property
    def session_cost(self) -> float:
        """Cumulative USD cost for the current session."""
        return self._session_cost

    def record_cost(self, cost_usd: float) -> None:
        """Add *cost_usd* to the session total."""
        self._session_cost += cost_usd

    def budget_exhausted(self) -> bool:
        """Return True if the session cost has hit the configured limit."""
        return self._session_cost >= self._cfg.get("budget_limit_usd", 5.00)

    def decide(
        self,
        prompt: str,
        override_provider: Optional[str] = None,
        override_model: Optional[str] = None,
        complexity_hint: Optional[float] = None,
    ) -> RoutingDecision:
        """Select provider and model for the given *prompt*.

        Priority:
        1. Manual overrides from the user.
        2. Budget enforcement → force local.
        3. Prefer local if under complexity threshold.
        4. Escalate to cloud fallback for complex prompts.

        Args:
            complexity_hint: When provided (0.0–1.0), overrides the automatic
                pattern-based complexity scorer. Sub-agents pass 1.0 here so
                delegated tasks always qualify for the most capable provider.
        """
        score = complexity_hint if complexity_hint is not None else _complexity_score(prompt)
        # If no health check has run yet, bootstrap from registered providers
        # rather than raising RuntimeError on first message after startup.
        available = self._registry.available_providers()
        if not available:
            available = list(self._registry.all().keys())

        # 1. Manual override
        if override_provider:
            model = override_model or self._get_default_model(override_provider)
            return RoutingDecision(
                provider=override_provider,
                model=model,
                reason="manual_override",
                complexity_score=score,
                estimated_cost_usd=0.0,
            )

        # 2. Budget exhausted → force local
        if self.budget_exhausted() and "ollama" in available:
            return RoutingDecision(
                provider="ollama",
                model=self._get_default_model("ollama"),
                reason="budget_exceeded_forcing_local",
                complexity_score=score,
                estimated_cost_usd=0.0,
            )

        prefer_local: bool = self._cfg.get("prefer_local", True)
        threshold: float = self._cfg.get("complexity_threshold", 0.65)

        # 3. Simple or prefer-local → use Ollama
        if prefer_local and score < threshold and "ollama" in available:
            return RoutingDecision(
                provider="ollama",
                model=self._get_default_model("ollama"),
                reason="local_capable",
                complexity_score=score,
                estimated_cost_usd=0.0,
            )

        # 4. Complex → cloud fallback
        fallback_provider = self._cfg.get("fallback_provider", "openai")
        fallback_model = self._cfg.get("fallback_model", "gpt-4o-mini")
        if fallback_provider in available:
            return RoutingDecision(
                provider=fallback_provider,
                model=override_model or fallback_model,
                reason="complexity_escalation",
                complexity_score=score,
                estimated_cost_usd=0.0,
            )

        # 5. Last resort — first available anything
        if available:
            provider = available[0]
            return RoutingDecision(
                provider=provider,
                model=self._get_default_model(provider),
                reason="last_resort_fallback",
                complexity_score=score,
                estimated_cost_usd=0.0,
            )

        raise RuntimeError("No available providers. Check your config and API keys.")

    def _get_default_model(self, provider_name: str) -> str:
        """Look up the default model for a provider from config or its class."""
        p = self._registry.get(provider_name)
        if p is None:
            return "unknown"
        models = p.list_models()
        return models[0] if models else "unknown"
