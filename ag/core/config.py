"""YAML config loader with env var expansion and validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_value(value: Any) -> Any:
    """Recursively expand ${VAR} placeholders in strings and nested dicts/lists."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(
            lambda m: os.environ.get(m.group(1), m.group(0)), value
        )
    if isinstance(value, dict):
        return {k: _expand_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_value(item) for item in value]
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


_DEFAULTS: dict = {
    "default_provider": "ollama",
    "default_model": "llama3.2:3b",
    "routing": {
        "prefer_local": True,
        "complexity_threshold": 0.65,
        "budget_limit_usd": 5.00,
        "fallback_provider": "openai",
        "fallback_model": "gpt-4o-mini",
    },
    "providers": {
        "ollama": {"enabled": True, "base_url": "http://localhost:11434", "timeout": 120},
    },
    "tools": {
        "shell": {"enabled": True, "require_confirm": True, "timeout": 30},
        "file_ops": {"enabled": True, "max_file_size_kb": 512},
        "web_search": {"enabled": True, "engine": "duckduckgo", "max_results": 5},
        "code_exec": {"enabled": True, "timeout": 30, "allow_network": False},
    },
    "ui": {
        "theme": "dark",
        "show_routing_decisions": True,
        "syntax_highlight": True,
        "stream_tokens": True,
    },
}


class Config:
    """Loaded and validated application configuration."""

    def __init__(self, data: dict) -> None:
        """Wrap raw config dict with convenience accessors."""
        self._data = data

    def __getitem__(self, key: str) -> Any:
        """Dict-style access."""
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-style get with default."""
        return self._data.get(key, default)

    @property
    def default_provider(self) -> str:
        """Default provider name."""
        return self._data.get("default_provider", "ollama")

    @property
    def default_model(self) -> str:
        """Default model name."""
        return self._data.get("default_model", "llama3.2:3b")

    @property
    def routing(self) -> dict:
        """Routing configuration section."""
        return self._data.get("routing", _DEFAULTS["routing"])

    @property
    def providers(self) -> dict:
        """Providers configuration section."""
        return self._data.get("providers", {})

    @property
    def tools(self) -> dict:
        """Tools configuration section."""
        return self._data.get("tools", _DEFAULTS["tools"])

    @property
    def ui(self) -> dict:
        """UI configuration section."""
        return self._data.get("ui", _DEFAULTS["ui"])


def load_config(path: Optional[str | Path] = None) -> Config:
    """Load config from YAML file, merge with defaults, expand env vars.

    Search order (first found wins):
    1. *path* argument
    2. ANTIGRAVITY_CONFIG env var
    3. ./config.yaml
    4. ~/.antigravity/config.yaml
    """
    search_paths: list[Path] = []
    if path:
        search_paths.append(Path(path))
    if env := os.environ.get("ANTIGRAVITY_CONFIG"):
        search_paths.append(Path(env))
    search_paths += [
        Path.cwd() / "config.yaml",
        Path.home() / ".antigravity" / "config.yaml",
    ]

    raw: dict = {}
    for p in search_paths:
        if p.exists():
            with p.open() as f:
                raw = yaml.safe_load(f) or {}
            break

    merged = _deep_merge(_DEFAULTS, raw)
    expanded = _expand_value(merged)
    return Config(expanded)
