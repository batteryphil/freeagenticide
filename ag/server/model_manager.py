"""Model manager — curated catalog + Ollama API bridge.

Provides:
  - A curated catalog of popular models with metadata (size, RAM requirement, tags)
  - Merging with the live Ollama /api/tags response to show install state
  - Streaming pull progress via Ollama /api/pull (NDJSON → async generator)
  - Model deletion via Ollama /api/delete
  - Active model get/set scoped to the server process

The active model is stored in a module-level variable so all WS sessions
(which share no persistent state) see the same selection.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import httpx

# ── Curated model catalog ─────────────────────────────────────────────────────
# Selected for coding assistant use cases; covers the full VRAM spectrum.
# Sizes are approximate compressed download sizes (not peak VRAM usage).
CATALOG: list[dict[str, Any]] = [
    # ── Sub-1B: for severely constrained hardware ──────────────────────────
    {
        "id": "qwen2.5:0.5b",
        "family": "Qwen 2.5",
        "size_gb": 0.4,
        "ram_gb": 1,
        "desc": "Ultra-fast 0.5B — good for autocomplete & quick Q&A.",
        "tags": ["fast", "minimal"],
        "recommended": False,
    },
    # ── 1–2B: daily driver on low-end ─────────────────────────────────────
    {
        "id": "qwen2.5:1.5b",
        "family": "Qwen 2.5",
        "size_gb": 1.0,
        "ram_gb": 2,
        "desc": "Fast 1.5B generalist. Good instruction following.",
        "tags": ["fast", "general"],
        "recommended": False,
    },
    {
        "id": "llama3.2:1b",
        "family": "Llama 3.2",
        "size_gb": 0.8,
        "ram_gb": 2,
        "desc": "Meta's 1B — fast, decent reasoning for its size.",
        "tags": ["fast", "general"],
        "recommended": False,
    },
    {
        "id": "llama3.2:3b",
        "family": "Llama 3.2",
        "size_gb": 2.0,
        "ram_gb": 4,
        "desc": "Meta's 3B — good balance of speed and quality.",
        "tags": ["general", "coding"],
        "recommended": False,
    },
    {
        "id": "phi4-mini:3.8b",
        "family": "Phi 4",
        "size_gb": 2.5,
        "ram_gb": 4,
        "desc": "Microsoft Phi-4 Mini — punches above its weight on reasoning.",
        "tags": ["reasoning", "coding"],
        "recommended": True,
    },
    # ── 4–8B: the sweet spot for most tasks ───────────────────────────────
    {
        "id": "qwen2.5:7b",
        "family": "Qwen 2.5",
        "size_gb": 4.7,
        "ram_gb": 8,
        "desc": "Strong 7B — excellent coding + instruction following.",
        "tags": ["coding", "general"],
        "recommended": True,
    },
    {
        "id": "qwen2.5-coder:7b",
        "family": "Qwen 2.5 Coder",
        "size_gb": 4.7,
        "ram_gb": 8,
        "desc": "Code-specialised Qwen 7B — state-of-art at this size.",
        "tags": ["coding"],
        "recommended": True,
    },
    {
        "id": "llama3.1:8b",
        "family": "Llama 3.1",
        "size_gb": 4.9,
        "ram_gb": 8,
        "desc": "Meta Llama 3.1 8B — versatile, great instruction following.",
        "tags": ["general", "coding"],
        "recommended": True,
    },
    {
        "id": "deepseek-coder-v2:16b",
        "family": "DeepSeek Coder V2",
        "size_gb": 8.9,
        "ram_gb": 12,
        "desc": "DeepSeek's V2 coder — HumanEval leader at this size.",
        "tags": ["coding"],
        "recommended": False,
    },
    {
        "id": "mistral:7b",
        "family": "Mistral",
        "size_gb": 4.1,
        "ram_gb": 8,
        "desc": "Mistral 7B Instruct v0.3 — fast & reliable.",
        "tags": ["general"],
        "recommended": False,
    },
    {
        "id": "gemma3:4b",
        "family": "Gemma 3",
        "size_gb": 2.5,
        "ram_gb": 5,
        "desc": "Google Gemma 3 4B — strong reasoning for its size.",
        "tags": ["general", "reasoning"],
        "recommended": False,
    },
    {
        "id": "gemma3:12b",
        "family": "Gemma 3",
        "size_gb": 7.0,
        "ram_gb": 12,
        "desc": "Google Gemma 3 12B — top-tier open model.",
        "tags": ["general", "reasoning", "coding"],
        "recommended": True,
    },
    # ── 13B+: high quality, needs ≥16GB RAM ───────────────────────────────
    {
        "id": "qwen2.5:14b",
        "family": "Qwen 2.5",
        "size_gb": 9.0,
        "ram_gb": 16,
        "desc": "Qwen 2.5 14B — near-GPT-4 quality on many coding benchmarks.",
        "tags": ["coding", "general"],
        "recommended": False,
    },
    {
        "id": "codellama:13b",
        "family": "Code Llama",
        "size_gb": 7.4,
        "ram_gb": 12,
        "desc": "Meta Code Llama 13B — deep code understanding.",
        "tags": ["coding"],
        "recommended": False,
    },
    {
        "id": "llama3.1:70b",
        "family": "Llama 3.1",
        "size_gb": 40.0,
        "ram_gb": 48,
        "desc": "Meta Llama 3.1 70B — near-GPT-4 quality (needs 48GB RAM).",
        "tags": ["general", "coding", "reasoning"],
        "recommended": False,
    },
    # ── Mixture-of-Experts ────────────────────────────────────────────────
    {
        "id": "mixtral:8x7b",
        "family": "Mixtral MoE",
        "size_gb": 26.0,
        "ram_gb": 32,
        "desc": "Mistral AI's 8×7B Sparse MoE — 12B active params per token, 32K context. "
                "Strong multilingual reasoning and coding.",
        "tags": ["general", "reasoning", "coding"],
        "recommended": False,
    },
    # ── Mamba SSM architecture ────────────────────────────────────────────
    {
        "id": "Hudson/falcon-mamba-instruct:7b-q4_0",
        "family": "Falcon-Mamba 7B",
        "size_gb": 4.2,
        "ram_gb": 8,
        "desc": "TII's Falcon-Mamba 7B — pure Mamba SSM (no attention heads), 1M context window. "
                "O(1) memory per token. Matches Llama 3.1 8B on benchmarks.",
        "tags": ["general", "fast", "mamba"],
        "recommended": True,
    },
    {
        "id": "sam860/jamba-reasoning",
        "family": "Jamba 3B",
        "size_gb": 2.0,
        "ram_gb": 4,
        "desc": "Hybrid Transformer+Mamba 3B with tool calling. Fast SSM recurrence "
                "for efficient reasoning with long context support.",
        "tags": ["reasoning", "fast", "mamba"],
        "recommended": False,
    },
]


# ── Active model state ────────────────────────────────────────────────────────
# Module-level — shared across all WS sessions in the same process.
_active_model: str = ""
_active_provider: str = "ollama"


def get_active_model() -> tuple[str, str]:
    """Return (model_id, provider_name) for the currently selected model."""
    return _active_model, _active_provider


def set_active_model(model_id: str, provider: str = "ollama") -> None:
    """Set the active model globally (all sessions see this)."""
    global _active_model, _active_provider
    _active_model = model_id
    _active_provider = provider


# ── Ollama API client ─────────────────────────────────────────────────────────

async def list_installed(ollama_url: str = "http://localhost:11434") -> list[dict]:
    """Fetch installed models from Ollama /api/tags.

    Returns:
        List of dicts with keys: name, size_bytes, modified_at.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ollama_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])
    except Exception:
        return []


async def pull_model(
    model_id: str,
    ollama_url: str = "http://localhost:11434",
) -> AsyncIterator[dict]:
    """Stream pull progress from Ollama /api/pull.

    Yields dicts with keys: status, completed (int), total (int), error (str).
    Ollama streams newline-delimited JSON during the pull.
    """
    payload = {"name": model_id, "stream": True}
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{ollama_url}/api/pull",
                json=payload,
                timeout=None,
            ) as resp:
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:
        yield {"status": "error", "error": str(exc)}


async def delete_model(
    model_id: str,
    ollama_url: str = "http://localhost:11434",
) -> dict:
    """Delete a model from Ollama.

    Returns:
        {"ok": True} on success or {"ok": False, "error": "..."}.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(
                "DELETE",
                f"{ollama_url}/api/delete",
                json={"name": model_id},
            )
            if resp.status_code in (200, 204):
                return {"ok": True}
            return {"ok": False, "error": resp.text}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def merge_catalog(installed: list[dict]) -> list[dict]:
    """Merge installed Ollama models with the curated catalog.

    Models in the catalog get an `installed` flag and their `installed_size_gb`.
    Models installed but not in the catalog are appended as user-installed entries.

    Args:
        installed: Raw response from Ollama /api/tags.

    Returns:
        Merged list ordered: installed-first, then catalog, then user-installed extras.
    """
    installed_names: dict[str, dict] = {}
    for m in installed:
        name = m.get("name", "")
        installed_names[name] = m

    # Tag catalog entries
    merged: list[dict] = []
    catalog_ids = set()
    for entry in CATALOG:
        model_id = entry["id"]
        catalog_ids.add(model_id)
        installed_info = installed_names.get(model_id)
        merged.append({
            **entry,
            "installed": installed_info is not None,
            "installed_size_gb": (
                round(installed_info["size"] / 1e9, 2) if installed_info else None
            ),
        })

    # Append user-installed models not in catalog
    for name, info in installed_names.items():
        if name not in catalog_ids:
            merged.append({
                "id": name,
                "family": name.split(":")[0].capitalize(),
                "size_gb": round(info["size"] / 1e9, 2),
                "ram_gb": None,
                "desc": "Locally installed model (not in catalog).",
                "tags": ["custom"],
                "recommended": False,
                "installed": True,
                "installed_size_gb": round(info["size"] / 1e9, 2),
            })

    # Sort: installed first, then recommended, then alphabetical
    merged.sort(key=lambda m: (not m["installed"], not m.get("recommended", False), m["id"]))
    return merged
