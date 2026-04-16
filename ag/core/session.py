"""Conversation session manager — context window and message history."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Context compaction — two-pass safe compactor ────────────────────────────
#
# Pass 1 — Tool Result Cap (fires unconditionally):
#   Any assistant message that is a tool result and exceeds MAX_TOOL_RESULT_CHARS
#   gets its content replaced with a stub notice.  This prevents any single tool
#   output (e.g. a 400-line file read) from dominating the context window.
#   The stub tells the LLM *which* tool produced the output and how to re-fetch
#   the specific part it needs (grep, targeted line-read, etc.).
#
# Pass 2 — MiddleOut (fires when total chars still exceed budget_tokens):
#   Keeps head (1/3) + tail (2/3) of conversation turns, drops middle.
#   Safe because Pass 1 ensures no individual message is pathologically large.
#   Drops whole messages — never slices mid-content.
#
# Reference: LoCoBench / LongBench-E (2026) show middle-out truncation is
# lethal for raw code files but acceptable for bounded conversational turns.
_CHARS_PER_TOKEN_ESTIMATE = 4   # conservative: 1 token ≈ 4 chars
_MAX_TOOL_RESULT_CHARS = 6_000  # ~1500 tokens — cap per tool output message

# Prefixes written by app._run_tool() that identify tool result messages
_TOOL_RESULT_PREFIXES = ("[Tool `", "[Tool result", "[Tool invoked")


def _char_len(messages: list[dict]) -> int:
    """Rough character count of all message content (no external deps)."""
    return sum(len(m.get("content", "")) for m in messages)


def _is_tool_result(msg: dict) -> bool:
    """Return True if this message is a tool result injected by _run_tool.

    Checks both role == 'assistant' and the content prefix.  User messages
    can share the same prefix format during session seeding — only assistant
    turns are capped.
    """
    if msg.get("role") != "assistant":
        return False
    content = msg.get("content", "")
    return any(content.startswith(p) for p in _TOOL_RESULT_PREFIXES)


def _cap_tool_results(
    messages: list[dict],
    max_chars: int = _MAX_TOOL_RESULT_CHARS,
) -> list[dict]:
    """Pass 1: Replace oversized tool result messages with a stub notice.

    The stub preserves the tool name so the LLM knows *what* output was
    dropped and can request a targeted re-fetch (grep/line-read/etc.).

    Args:
        messages: API-formatted message dicts.
        max_chars: Per-message character cap for tool result content.

    Returns:
        New list; non-tool messages and small tool results are unchanged.
    """
    out = []
    for msg in messages:
        if msg.get("role") == "assistant" and _is_tool_result(msg):
            content = msg.get("content", "")
            if len(content) > max_chars:
                # Extract first line for the tool name reference
                first_line = content.splitlines()[0] if content else ""
                stub = (
                    f"{first_line}\n"
                    f"[Output truncated: {len(content):,} chars exceeded the "
                    f"{max_chars:,}-char per-result limit. "
                    f"Use file_ops with operation='grep' or 'read' with a "
                    f"specific path/pattern to retrieve the relevant section.]"
                )
                out.append({**msg, "content": stub})
                continue
        out.append(msg)
    return out


def _middle_out_compact(
    messages: list[dict],
    budget_tokens: int,
) -> list[dict]:
    """Two-pass compactor: tool-result cap then middle-out.

    Args:
        messages: API-formatted message dicts.
        budget_tokens: Approximate token budget for the whole message list.

    Returns:
        Compacted list. Whole messages are dropped — content is never sliced.
    """
    # Pass 1: cap any oversized tool result blocks (always runs)
    capped = _cap_tool_results(messages)

    # Pass 2: middle-out if still over budget
    budget_chars = budget_tokens * _CHARS_PER_TOKEN_ESTIMATE
    if _char_len(capped) <= budget_chars:
        return capped

    system_msgs = [m for m in capped if m.get("role") == "system"]
    non_system = [m for m in capped if m.get("role") != "system"]

    if len(non_system) <= 4:
        return capped  # too short to compact meaningfully

    head_size = max(1, len(non_system) // 3)
    tail_size = len(non_system) - head_size
    head = non_system[:head_size]
    tail = non_system[-tail_size:] if tail_size > 0 else []

    compacted = system_msgs + head + tail

    # If still over budget, trim head one message at a time
    while _char_len(compacted) > budget_chars and len(head) > 1:
        head = head[:-1]
        compacted = system_msgs + head + tail

    return compacted


@dataclass
class Message:
    """A single conversation message."""

    role: str   # "user" | "assistant" | "system"
    content: str
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class Session:
    """Manages the active conversation, token budget, and context window."""

    SYSTEM_PROMPT: str = (
        "You are Antigravity, a powerful AI coding assistant. "
        "You help the user write, debug, and understand code. "
        "Be concise, accurate, and always provide working examples."
    )

    def __init__(
        self,
        max_context_messages: int = 40,
        system: Optional[str] = None,
        seed_messages: Optional[list[Message]] = None,
        context_token_limit: int = 6000,
    ) -> None:
        """Initialise an empty session with an optional system prompt.

        Args:
            max_context_messages: Hard cap on stored message count.
            system: Override system prompt (defaults to SYSTEM_PROMPT).
            seed_messages: Pre-populate history (used for child agent inheritance).
            context_token_limit: Approximate token budget for to_api_messages().
                MiddleOutTruncator activates when this is exceeded.
                Default 6000 is safe for llama3.2:1b (8K context) and
                qwen2.5:0.5b (4K context — set lower for that model).
        """
        self._messages: list[Message] = []
        if seed_messages:
            self._messages.extend(seed_messages)
        self._max_context = max_context_messages
        self._system = system or self.SYSTEM_PROMPT
        self._context_token_limit = context_token_limit
        self._total_tokens_in: int = 0
        self._total_tokens_out: int = 0
        self._total_cost: float = 0.0

    # ── Message management ────────────────────────────────────────────────────

    def add_user(self, content: str) -> None:
        """Append a user turn."""
        self._messages.append(Message(role="user", content=content))
        self._trim()

    def add_assistant(
        self,
        content: str,
        provider: str = "",
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Append an assistant turn with optional accounting info."""
        self._messages.append(
            Message(
                role="assistant",
                content=content,
                provider=provider,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
            )
        )
        self._total_tokens_in += tokens_in
        self._total_tokens_out += tokens_out
        self._total_cost += cost_usd
        self._trim()

    def to_api_messages(self) -> list[dict]:
        """Return messages formatted for the LLM API (role + content dicts).

        Applies MiddleOutTruncator automatically when the conversation exceeds
        ``context_token_limit``.  The system prompt is always absent here —
        providers receive it separately via ``CompletionRequest.system``.
        """
        raw = [{"role": m.role, "content": m.content} for m in self._messages]
        return _middle_out_compact(raw, self._context_token_limit)

    def system_prompt(self) -> str:
        """Return the current system prompt."""
        return self._system

    def set_system(self, prompt: str) -> None:
        """Update the system prompt."""
        self._system = prompt

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def total_cost(self) -> float:
        """Cumulative session cost in USD."""
        return self._total_cost

    @property
    def total_tokens(self) -> tuple[int, int]:
        """Total (tokens_in, tokens_out) for the session."""
        return self._total_tokens_in, self._total_tokens_out

    @property
    def message_count(self) -> int:
        """Number of messages in the history."""
        return len(self._messages)

    def last_n(self, count: int) -> list[Message]:
        """Return up to the last N messages from history."""
        if count <= 0:
            return []
        return list(self._messages[-count:])

    def clear(self) -> None:
        """Wipe the conversation history (keep system prompt)."""
        self._messages.clear()
        self._total_tokens_in = 0
        self._total_tokens_out = 0
        self._total_cost = 0.0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _trim(self) -> None:
        """Keep the context within the configured window size."""
        if len(self._messages) > self._max_context:
            # Always keep the first user message for context continuity
            self._messages = (
                self._messages[:1] + self._messages[-(self._max_context - 1):]
            )
