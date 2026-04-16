"""Recursive Agent — runs a message loop and delegates to sub-agents via tools."""

from __future__ import annotations

import json
import re
from typing import Any, TYPE_CHECKING

from ag.core.context import AgentContext, AgentChunk
from ag.core.session import Session
from ag.core.spawn import AgentProfile
from ag.providers.base import CompletionRequest, BaseProvider

if TYPE_CHECKING:
    from ag.tools.registry import ToolRegistry


# Maximum tokens to allow in a single message loop before forcing a response
_MAX_LOOP_ITERATIONS = 12

# Regex to extract JSON tool calls from LLM response text.
# Supports both fenced ```json blocks and raw JSON objects.
_TOOL_CALL_RE = re.compile(
    r"```json\s*(\{.*?\})\s*```"
    r"|"
    r"(\{[^`]*?\"tool_name\"[^`]*?\})",
    re.DOTALL,
)

# Regex to extract runnable code blocks when the model skips tool calls.
# Group 1 = language specifier (may be empty for plain ``` blocks).
# Group 2 = code content.
_CODE_BLOCK_RE = re.compile(
    r"```(python|javascript|js|typescript|ts|bash|sh|html|rust|go|py)?\s*\n([\s\S]*?)```",
    re.IGNORECASE,
)

# Language aliases → canonical runner language
_LANG_ALIAS: dict[str, str] = {
    "js": "javascript",
    "ts": "typescript",
    "sh": "bash",
    "py": "python",
    "": "python",   # untagged blocks default to Python
    None: "python",  # untagged blocks default to Python
}

# Keywords that suggest the code is not Python (to avoid mislabelling)
_JS_KEYWORDS = re.compile(r"\bconst\b|\blet\b|\bconsole\.log\b|\bfunction\b")
_BASH_KEYWORDS = re.compile(r"^#!.*bash|^echo\b|^\$\s", re.MULTILINE)


def _infer_language(code: str) -> str:
    """Guess language for untagged code blocks."""
    if _BASH_KEYWORDS.search(code):
        return "bash"
    if _JS_KEYWORDS.search(code):
        return "javascript"
    return "python"


def _build_subagent_context_prompt(profiles: list[AgentProfile]) -> str:
    """Build the sub-agent catalogue injected into the system prompt."""
    if not profiles:
        return ""
    lines = [
        "\n\n## Available Sub-Agents",
        "You can delegate tasks to specialised sub-agents via the `call_subordinate` tool.",
        "Available agents:\n",
    ]
    for p in profiles:
        lines.append(f"- **{p.name}** ({p.title}): {p.context.strip()}")
    lines.append(
        "\nUse `call_subordinate` when the task clearly benefits from specialisation."
    )
    return "\n".join(lines)


class Agent:
    """A single LLM agent that can call tools and spawn sub-agents.

    Key design points:
    - `context` is the shared mutable state across the entire agent tree.
    - `depth` is an immutable constructor argument, not stored on context.
    - Token costs are accumulated directly on `context` during `message_loop`.
    - `session` is owned exclusively by this agent instance.
    """

    def __init__(
        self,
        profile: AgentProfile,
        context: AgentContext,
        provider: BaseProvider,
        session: Session,
        tools: ToolRegistry,
        depth: int = 0,
        max_depth: int = 4,
    ) -> None:
        """Initialise the agent."""
        self.profile = profile
        self.context = context
        self._provider = provider
        self._session = session
        self._tools = tools
        self.depth = depth
        self.max_depth = max_depth

    # ── Public API ─────────────────────────────────────────────────────────────

    async def message_loop(self, user_message: str) -> str:
        """Run the agent until it produces a final (non-tool) response.

        Returns the final assistant response as a plain string.
        """
        self._session.add_user(user_message)
        iterations = 0

        while iterations < _MAX_LOOP_ITERATIONS:
            iterations += 1
            response_text = await self._call_llm()

            # Check for explicit tool call first
            tool_call = _extract_tool_call(response_text)

            # ── Auto-run interception ─────────────────────────────────────────
            # If the model returned a code block without calling write_to_editor
            # or run_in_ui, do it automatically so any model acts agentic.
            if tool_call is None and self.depth == 0:
                code_block = _extract_code_block(response_text)
                if code_block is not None:
                    lang, code = code_block
                    # Synthesise sequential tool calls
                    tool_call = {
                        "tool_name": "write_to_editor",
                        "tool_args": {"code": code, "language": lang},
                    }

            if tool_call is None:
                # No tool call, no code block → this is the final response
                self._session.add_assistant(response_text)
                return response_text

            # Emit the tool-call text so the TUI can show it dimmed
            self._emit(response_text, is_tool_call=True)

            # Execute the tool
            tool_name = tool_call.get("tool_name", "")
            tool_args = tool_call.get("tool_args", {})
            tool_result_text = await self._dispatch_tool(tool_name, tool_args)

            # After write_to_editor, immediately auto-chain run_in_ui
            if tool_name == "write_to_editor" and "code" in tool_args:
                run_result = await self._dispatch_tool(
                    "run_in_ui",
                    {"code": tool_args["code"], "language": tool_args.get("language", "python")},
                )
                tool_result_text += "\n" + run_result

            # Feed result back into context as a user turn
            self._session.add_user(
                f"[Tool result from `{tool_name}`]\n{tool_result_text}"
            )

        # Safety: exceeded max iterations — return what we have
        return "[Agent exceeded max loop iterations without producing a final response.]"

    # ── Private ────────────────────────────────────────────────────────────────

    async def _call_llm(self) -> str:
        """Call the provider and stream chunks, returning the complete text."""
        system = self._build_system_prompt()
        request = CompletionRequest(
            messages=self._session.to_api_messages(),
            model=self.profile.model,
            temperature=self.profile.temperature,
            system=system,
        )

        response_text = ""
        async for chunk in self._provider.complete(request):
            if not chunk.is_final:
                response_text += chunk.text
                self._emit(chunk.text)
            else:
                # Accumulate costs onto the shared context
                self.context.total_cost_usd += chunk.cost_usd
                self.context.tokens_in += chunk.tokens_in
                self.context.tokens_out += chunk.tokens_out

        return response_text

    def _emit(
        self,
        text: str,
        is_tool_call: bool = False,
        is_tool_result: bool = False,
        is_final: bool = False,
    ) -> None:
        """Fire a chunk notification to the TUI callback if registered."""
        if self.context.output_callback:
            self.context.output_callback(
                AgentChunk(
                    text=text,
                    agent_name=self.profile.name,
                    depth=self.depth,
                    is_tool_call=is_tool_call,
                    is_tool_result=is_tool_result,
                    is_final=is_final,
                )
            )

    async def _dispatch_tool(self, tool_name: str, tool_args: dict) -> str:
        """Look up and execute a tool by name. Returns result text."""
        # call_subordinate is handled natively — it needs access to self
        if tool_name == "call_subordinate":
            return await self._call_subordinate(**tool_args)

        tool = self._tools.get(tool_name)
        if tool is None:
            return f"Error: unknown tool `{tool_name}`."

        result = await tool.run(**tool_args)
        self._emit(result.output, is_tool_result=True)

        if result.success:
            return result.output
        return f"Error from `{tool_name}`: {result.error or result.output}"

    async def _call_subordinate(
        self,
        message: str,
        agent_profile: str = "developer",
        reset: bool = True,
        context_msgs: int = 6,
        **_: Any,
    ) -> str:
        """Spawn a sub-agent, delegate *message*, and return its response."""
        if self.depth >= self.max_depth:
            return (
                f"Error: max agent nesting depth ({self.max_depth}) reached. "
                "Cannot spawn further sub-agents."
            )

        # Resolve profile
        from ag.core.spawn import load_profile

        try:
            profile = load_profile(agent_profile)
        except FileNotFoundError as exc:
            return f"Error: {exc}"

        if not profile.enabled:
            return f"Error: agent profile '{agent_profile}' is disabled."

        # Resolve provider — profile pin > router fallback (complexity=1.0)
        child_provider = self._resolve_provider(profile, message)

        # Build child session
        if reset:
            child_session = Session(system=profile.system_prompt or None)
        else:
            child_session = Session(
                system=profile.system_prompt or None,
                seed_messages=self._session.last_n(context_msgs),
            )

        # Spawn child — pass the same context instance (shared reference)
        child = Agent(
            profile=profile,
            context=self.context,       # ← same object, not a copy
            provider=child_provider,
            session=child_session,
            tools=self._tools,
            depth=self.depth + 1,
            max_depth=self.max_depth,
        )

        # Emit spawn announcement to TUI
        indent = "  " * (self.depth + 1)
        self._emit(
            f"\n{indent}▸ Delegating to **{profile.title}** agent…\n",
            is_tool_call=True,
        )

        response = await child.message_loop(message)

        self._emit(
            f"\n{indent}◂ **{profile.title}** returned.\n",
            is_tool_result=True,
        )
        return response

    def _resolve_provider(self, profile: AgentProfile, message: str) -> BaseProvider:
        """Resolve which provider to use for a child agent.

        Priority:
          1. Profile pin (provider + model) if available and healthy
          2. Router decide() with complexity_hint=1.0 (sub-tasks are complex)
        """
        if profile.provider:
            pinned = self.context.registry.get(profile.provider)
            if pinned is not None:
                # Budget still applies
                budget = self.context.router.config.get("budget_limit_usd", 5.0)
                if self.context.total_cost_usd < budget:
                    return pinned
            # Fall through to router if pin is unavailable or over budget

        decision = self.context.router.decide(message, complexity_hint=1.0)
        provider = self.context.registry.get(decision.provider)
        if provider is None:
            # Absolute last resort — return parent's own provider
            return self._provider
        return provider

    def _build_system_prompt(self) -> str:
        """Build the full system prompt for this agent's LLM calls."""
        base = self._session.system_prompt()

        # Append profile-specific specialisation instructions
        if self.profile.system_prompt:
            base = base + "\n\n" + self.profile.system_prompt

        # ── Tool schemas ────────────────────────────────────────────────────────
        # Inject available tools + exact call syntax.  Small local models need
        # explicit examples — they will not infer the JSON format on their own.
        tool_schemas = self._tools.schemas()
        if tool_schemas:
            base += "\n\n### Available Tools\n"
            base += (
                "You have access to the following tools. "
                "To execute a tool, your response MUST contain a JSON block "
                "using EXACTLY this structure:\n\n"
                "```json\n"
                '{"tool_name": "<name>", "tool_args": {<args>}}\n'
                "```\n\n"
                "**One tool call per turn. Never combine a tool call with prose. "
                "After the tool result is returned, continue reasoning.**\n\n"
                "**Available tools:**\n"
            )
            for schema in tool_schemas:
                fn = schema.get("function", schema)
                name = fn.get("name", "unknown")
                desc = fn.get("description", "")
                props = fn.get("parameters", {}).get("properties", {})
                arg_names = ", ".join(f'"{k}": ...' for k in props)
                base += (
                    f"\n- **{name}**: {desc}\n"
                    f"  Example: "
                    f'`{{"tool_name": "{name}", "tool_args": {{{arg_names}}}}}`\n'
                )

        # ── Sub-agent catalogue (root agent only) ───────────────────────────────
        # Children don't get the catalogue — they are single-purpose workers.
        if self.depth == 0 and self.depth < self.max_depth:
            from ag.core.spawn import list_profiles

            profiles = [p for p in list_profiles() if p.name != "default"]
            catalogue = _build_subagent_context_prompt(profiles)
            if catalogue:
                base += catalogue
                base += (
                    "\n\n### Delegating to Sub-Agents\n"
                    "Use `call_subordinate` to delegate to a specialised agent:\n"
                    "```json\n"
                    '{"tool_name": "call_subordinate", "tool_args": '
                    '{"message": "<task>", "agent_profile": "<name>"}}\n'
                    "```\n"
                    "Produce a tool call OR a final answer — never both in the same turn."
                )

        return base



def _extract_tool_call(text: str) -> dict | None:
    """Extract the first JSON tool-call dict from *text*, or None."""
    for match in _TOOL_CALL_RE.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw:
            try:
                parsed = json.loads(raw.strip())
                if "tool_name" in parsed:
                    return parsed
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def _extract_code_block(text: str) -> tuple[str, str] | None:
    """Extract the first runnable code block from *text*.

    Returns (language, code) or None if no runnable code block found.
    Handles both tagged (```python) and untagged (```) fenced blocks.
    """
    match = _CODE_BLOCK_RE.search(text)
    if match is None:
        return None
    lang_raw = (match.group(1) or "").lower()
    code = match.group(2).rstrip()
    if not code.strip():
        return None  # empty block — ignore
    if lang_raw in _LANG_ALIAS:
        lang = _LANG_ALIAS[lang_raw]
    else:
        lang = lang_raw or _infer_language(code)
    return lang, code
