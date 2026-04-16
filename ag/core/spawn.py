"""Agent profile loader — discovers and merges agent.yaml profile definitions.

Directory resolution order (lowest → highest priority):
  1. ag/agents/<name>/          built-in default profiles
  2. ag/agents_user/<name>/     user overrides
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Built-in profile directory (shipped with the package)
_DEFAULT_PROFILES_DIR = Path(__file__).parent.parent / "agents"
# User-defined overrides (ignored by git)
_USER_PROFILES_DIR = Path(__file__).parent.parent / "agents_user"


@dataclass
class AgentProfile:
    """Resolved agent profile after full directory cascade merge."""

    name: str
    title: str = ""
    description: str = ""
    # Injected into parent's system prompt so LLM knows this agent exists
    context: str = ""
    # Merged system prompt override (empty = use default Antigravity prompt)
    system_prompt: str = ""
    # Optional provider/model pin; None = delegate to router
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.35
    enabled: bool = True
    # Source directories this profile was merged from
    origins: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Ensure title falls back to name if omitted."""
        if not self.title:
            self.title = self.name


def load_profile(name: str) -> AgentProfile:
    """Load and merge a named profile from all relevant directories.

    Raises FileNotFoundError if no definition exists in any directory.
    """
    default = _load_profile_from_dir(_DEFAULT_PROFILES_DIR, name, "default")
    user = _load_profile_from_dir(_USER_PROFILES_DIR, name, "user")

    if default is None and user is None:
        raise FileNotFoundError(
            f"No agent profile '{name}' found in:\n"
            f"  {_DEFAULT_PROFILES_DIR}\n"
            f"  {_USER_PROFILES_DIR}"
        )

    if default is None:
        assert user is not None
        return user
    if user is None:
        return default

    return _merge_profiles(default, user)


def list_profiles() -> list[AgentProfile]:
    """Return all known agent profiles (merged, enabled only)."""
    names: set[str] = set()
    for d in (_DEFAULT_PROFILES_DIR, _USER_PROFILES_DIR):
        if d.exists():
            for subdir in d.iterdir():
                if subdir.is_dir() and not subdir.name.startswith("_"):
                    names.add(subdir.name)

    profiles: list[AgentProfile] = []
    for name in sorted(names):
        try:
            p = load_profile(name)
            if p.enabled:
                profiles.append(p)
        except Exception:
            continue
    return profiles


def _load_profile_from_dir(
    base: Path, name: str, origin: str
) -> AgentProfile | None:
    """Load a single profile from *base*/<name>/.  Returns None if absent."""
    profile_dir = base / name
    yaml_path = profile_dir / "agent.yaml"

    if not profile_dir.exists():
        return None

    data: dict = {}
    if yaml_path.exists():
        try:
            data = yaml.safe_load(yaml_path.read_text()) or {}
        except Exception:
            data = {}

    data["name"] = name
    data["origins"] = [origin]

    # Merge prompt shards from prompts/ subdirectory in sort order
    prompts_dir = profile_dir / "prompts"
    if prompts_dir.exists():
        shards = sorted(prompts_dir.glob("*.md"))
        if shards:
            data["system_prompt"] = "\n\n".join(
                p.read_text().strip() for p in shards
            )

    # Whitelist only known fields
    known = AgentProfile.__dataclass_fields__.keys()
    filtered = {k: v for k, v in data.items() if k in known}
    return AgentProfile(**filtered)


def _merge_profiles(base: AgentProfile, override: AgentProfile) -> AgentProfile:
    """Merge *override* on top of *base*. Non-empty override values win."""
    return AgentProfile(
        name=override.name,
        title=override.title or base.title,
        description=override.description or base.description,
        context=override.context or base.context,
        # Prompt shards: override wins wholesale if non-empty
        system_prompt=override.system_prompt or base.system_prompt,
        provider=override.provider or base.provider,
        model=override.model or base.model,
        temperature=override.temperature if override.temperature != 0.35 else base.temperature,
        enabled=override.enabled if not override.enabled else base.enabled,
        origins=base.origins + override.origins,
    )
