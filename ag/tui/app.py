"""Main Textual application — assembles all panels and drives inference."""

from __future__ import annotations

import asyncio
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, Static

from ag.core.config import Config
from ag.core.router import Router
from ag.core.session import Session
from ag.core.context import AgentContext, AgentChunk
from ag.core.agent import Agent
from ag.core.spawn import load_profile
from ag.providers.registry import ProviderRegistry
from ag.tools.registry import ToolRegistry
from ag.tui.chat_panel import ChatPanel, ChatMessage
from ag.tui.cost_panel import CostPanel
from ag.tui.provider_panel import ProviderPanel, ProviderChanged


# ── Slash command descriptions ────────────────────────────────────────────────
_SLASH_HELP = """\
/help        Show this help
/clear       Clear conversation history
/provider X  Switch to provider X  (e.g. /provider openai)
/model X     Switch to model X     (e.g. /model gpt-4o)
/health      Re-run provider health checks
/cost        Show session cost summary
/search X    Web search for X
/run CMD     Execute shell command CMD (shows confirmation prompt)
/yes         Confirm a pending shell command
/n           Cancel a pending shell command
/read PATH   Read a file into chat
/quit        Exit Antigravity-Local
"""


class AntigravityApp(App):
    """Antigravity-Local — multi-provider AI coding assistant TUI."""

    TITLE = "Antigravity-Local"
    CSS = """
    Screen {
        background: #0a0a14;
    }
    Header {
        background: #1a1a2e;
        color: #a0a0ff;
        text-style: bold;
        height: 1;
    }
    Footer {
        background: #1a1a2e;
        color: #6666aa;
        height: 1;
    }
    #main-layout {
        layout: horizontal;
        height: 1fr;
    }
    #center-col {
        layout: vertical;
        width: 1fr;
    }
    #input-row {
        height: 3;
        layout: horizontal;
        border: solid #2a2a3e;
        background: #0f0f1a;
        padding: 0 1;
    }
    #prompt-label {
        width: 4;
        color: #7777ff;
        content-align: center middle;
    }
    #msg-input {
        width: 1fr;
        border: none;
        background: transparent;
        color: #e0e0ff;
    }
    #status-bar {
        height: 1;
        background: #141428;
        color: #5555aa;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("ctrl+h", "health_check", "Health"),
        Binding("escape", "focus_input", "Focus Input"),
    ]

    def __init__(self, config: Config) -> None:
        """Initialise app with loaded config."""
        super().__init__()
        self._config = config
        self._registry = ProviderRegistry(config.providers)
        self._router = Router(config.routing, self._registry)
        self._session = Session()
        self._tools = ToolRegistry(config.tools)
        self._active_provider: str = config.default_provider
        self._active_model: str = config.default_model
        # Flags: True only when the user has *explicitly* chosen a provider/model
        self._user_override_provider: bool = False
        self._user_override_model: bool = False
        # Pending shell command waiting for /yes or /n confirmation.
        self._pending_shell_command: str | None = None
        self._streaming = False

        # Shared agent tree context — single instance for the whole session
        self._agent_context = AgentContext(
            session_id=id(self._session).__str__(),
            registry=self._registry,
            router=self._router,
            tools=self._tools,
        )
        # Active streaming message widgets keyed by (agent_name, depth)
        self._active_chunks: dict[tuple[str, int], ChatMessage] = {}

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        """Build the three-column layout."""
        yield Header()
        with Horizontal(id="main-layout"):
            yield ProviderPanel(id="provider-panel")
            with Vertical(id="center-col"):
                yield ChatPanel(id="chat-panel")
                with Horizontal(id="input-row"):
                    yield Label("❯", id="prompt-label")
                    yield Input(placeholder="Message Antigravity... (/help for commands)", id="msg-input")
                yield Static("Ready  •  Ctrl+C quit  •  Ctrl+H health check", id="status-bar")
            yield CostPanel(id="cost-panel")
        yield Footer()

    # ── Startup ───────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Focus the input and run initial health check."""
        self.query_one("#msg-input", Input).focus()
        self.run_health_check()

    # ── Input handling ────────────────────────────────────────────────────────

    @on(Input.Submitted, "#msg-input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Route submitted input to slash-command handler or LLM."""
        text = event.value.strip()
        if not text:
            return
        inp = self.query_one("#msg-input", Input)
        inp.value = ""

        if text.startswith("/"):
            await self._handle_slash(text)
        else:
            await self._handle_chat(text)

    async def _handle_slash(self, text: str) -> None:
        """Dispatch /commands."""
        parts = text.split(maxsplit=1)
        cmd = parts[0].lstrip("/").lower()
        arg = parts[1] if len(parts) > 1 else ""
        chat = self.query_one("#chat-panel", ChatPanel)

        if cmd == "help":
            msg = chat.add_assistant_message("system", "help")
            msg.append_text(_SLASH_HELP)
        elif cmd == "clear":
            self.action_clear_chat()
        elif cmd == "provider" and arg:
            # Explicit user override — engage the flag so router respects it.
            self._active_provider = arg
            self._user_override_provider = True
            self._user_override_model = False   # reset model when provider changes
            self._update_status(f"Switched to provider: {arg}")
        elif cmd == "model" and arg:
            self._active_model = arg
            self._user_override_model = True
            self._update_status(f"Switched to model: {arg}")
        elif cmd == "health":
            self.run_health_check()
        elif cmd == "cost":
            tin, tout = self._session.total_tokens
            info = f"Session: {tin} in / {tout} out tokens · ${self._session.total_cost:.4f}"
            msg = chat.add_assistant_message("system", "cost")
            msg.append_text(info)
        elif cmd in ("search", "s") and arg:
            await self._run_tool("web_search", query=arg)
        elif cmd in ("run", "shell") and arg:
            await self._request_shell_confirm(arg)
        elif cmd == "read" and arg:
            await self._run_tool("file_ops", operation="read", path=arg)
        # Shell confirmation responses
        elif cmd in ("yes", "y") and self._pending_shell_command:
            pending = self._pending_shell_command
            self._pending_shell_command = None
            await self._run_tool("shell", command=pending, confirmed=True)
        elif cmd in ("no", "n") and self._pending_shell_command:
            self._pending_shell_command = None
            self._update_status("Shell command cancelled.")
        elif cmd in ("quit", "exit", "q"):
            self.exit()
        else:
            self._update_status(f"Unknown command: {text}")

    async def _handle_chat(self, text: str) -> None:
        """Process a normal chat message through the agent tree."""
        if self._streaming:
            self._update_status("Streaming in progress — please wait.")
            return

        chat = self.query_one("#chat-panel", ChatPanel)
        chat.add_user_message(text)
        self._session.add_user(text)

        # Route to decide provider for the root agent
        decision = self._router.decide(
            text,
            override_provider=self._active_provider if self._user_override_provider else None,
            override_model=self._active_model if self._user_override_model else None,
        )
        provider = self._registry.get(decision.provider)
        if provider is None:
            chat.add_tool_annotation(
                f"⚠️ Provider '{decision.provider}' unavailable.", depth=0
            )
            return

        self._update_status(
            f"Routing → {decision.provider}/{decision.model}  "
            f"[complexity={decision.complexity_score:.2f}  reason={decision.reason}]"
        )

        # Wire the chunk callback so every AgentChunk routes to the chat panel
        self._active_chunks.clear()

        def _on_chunk(chunk: AgentChunk) -> None:
            """Dispatch an AgentChunk to the depth-aware chat panel."""
            chat.route_chunk(chunk, self._active_chunks)
            # Mirror root-agent cost to the router's session tracker
            if chunk.depth == 0 and chunk.is_final:
                self._router.record_cost(self._agent_context.total_cost_usd)

        self._agent_context.output_callback = _on_chunk

        # Build profile for root agent
        try:
            profile = load_profile("default")
        except FileNotFoundError:
            from ag.core.spawn import AgentProfile
            profile = AgentProfile(name="default")

        # Override temperature from decision if available
        profile.provider = decision.provider
        profile.model = decision.model

        root_agent = Agent(
            profile=profile,
            context=self._agent_context,
            provider=provider,
            session=self._session,
            tools=self._tools,
            depth=0,
            max_depth=4,
        )

        self._run_agent(root_agent, text)

    @work(exclusive=False)
    async def _run_agent(self, agent: Agent, message: str) -> None:
        """Background worker: run the agent message loop."""
        self._streaming = True
        try:
            await agent.message_loop(message)
        except Exception as exc:
            chat = self.query_one("#chat-panel", ChatPanel)
            chat.add_tool_annotation(f"⚠️ Agent error: {exc}", depth=0)
        finally:
            self._streaming = False
            cost = self._agent_context.total_cost_usd
            tin = self._agent_context.tokens_in
            tout = self._agent_context.tokens_out
            try:
                cost_panel = self.query_one("#cost-panel", CostPanel)
                cost_panel.record_usage(
                    tokens_in=tin,
                    tokens_out=tout,
                    cost_usd=cost,
                    provider=self._active_provider,
                    model=self._active_model,
                    reason="agent_tree",
                    complexity=0.0,
                )
            except Exception:
                pass
            self._update_status(
                f"Done — ${cost:.4f} total · {tin}/{tout} tokens"
            )

    async def _request_shell_confirm(self, command: str) -> None:
        """Display a confirmation prompt before executing a shell command."""
        self._pending_shell_command = command
        chat = self.query_one("#chat-panel", ChatPanel)
        chat.add_tool_annotation(
            f"⚠️  **Shell command requires confirmation:**\n"
            f"```\n{command}\n```\n"
            f"Type `/yes` to run or `/n` to cancel.",
            depth=0,
        )
        self._update_status(f"Awaiting confirmation for: {command[:60]}")


    async def _run_tool(self, tool_name: str, **kwargs) -> None:
        """Execute a tool, display in the chat, and persist to session memory.

        Writing both the command and result to ``self._session`` ensures the
        next LLM turn can see what the user just loaded/searched/executed.
        Without this, the LLM is blind to every slash-command action.
        """
        chat = self.query_one("#chat-panel", ChatPanel)
        result = await self._tools.run(tool_name, **kwargs)

        # Build a human-readable label for the session (e.g. "read app.py")
        label_parts = [tool_name.replace("_", " ")]
        for v in list(kwargs.values())[:2]:
            if isinstance(v, str):
                label_parts.append(str(v)[:80])
        command_label = " ".join(label_parts)

        # Persist as a user message so the LLM knows the intent
        self._session.add_user(f"[Tool invoked: {command_label}]")

        msg = chat.add_assistant_message("tool", tool_name)
        if result.success:
            output_text = result.output or "(no output)"
            msg.append_text(f"```\n{output_text}\n```")
            # Persist the result as an assistant turn the LLM can reference
            self._session.add_assistant(
                f"[Tool `{tool_name}` result]\n{output_text}",
                provider="tool",
                model=tool_name,
            )
        else:
            error_text = f"⚠️ Tool error: {result.error}"
            msg.append_text(error_text)
            self._session.add_assistant(
                f"[Tool `{tool_name}` error]\n{result.error}",
                provider="tool",
                model=tool_name,
            )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_clear_chat(self) -> None:
        """Clear the session and wipe visible chat history."""
        self._session.clear()
        chat = self.query_one("#chat-panel", ChatPanel)
        for widget in chat.query(ChatMessage):
            widget.remove()
        self._update_status("Conversation cleared.")

    def action_health_check(self) -> None:
        """Trigger a health check."""
        self.run_health_check()

    def action_focus_input(self) -> None:
        """Focus the message input box."""
        self.query_one("#msg-input", Input).focus()

    # ── Health check ──────────────────────────────────────────────────────────

    @work(exclusive=True)
    async def run_health_check(self) -> None:
        """Run provider health checks and update the sidebar."""
        self._update_status("Running health checks…")
        health = await self._registry.check_all()
        provider_panel = self.query_one("#provider-panel", ProviderPanel)
        provider_panel.update_health(health)
        available = [n for n, h in health.items() if h.available]
        self._update_status(f"Health OK — available: {', '.join(available) or 'none'}")

        # Update model list for active provider
        active_health = health.get(self._active_provider)
        if active_health and active_health.models:
            provider_panel.update_models(active_health.models)
            if active_health.models:
                self._active_model = active_health.models[0]

        # Also set budget on cost panel
        cost_panel = self.query_one("#cost-panel", CostPanel)
        cost_panel.set_budget(self._config.routing.get("budget_limit_usd", 5.00))

    @on(ProviderChanged)
    async def on_provider_changed(self, event: ProviderChanged) -> None:
        """React to user picking a new provider in the sidebar."""
        self._active_provider = event.provider
        # Sidebar selection counts as an explicit user override.
        self._user_override_provider = True
        self._user_override_model = False  # reset model when provider changes
        health = self._registry.last_health()
        h = health.get(event.provider)
        if h and h.models:
            self.query_one("#provider-panel", ProviderPanel).update_models(h.models)
            self._active_model = h.models[0]
        self._update_status(f"Provider → {event.provider}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_status(self, msg: str) -> None:
        """Update the bottom status bar."""
        self.query_one("#status-bar", Static).update(f" {msg}")
