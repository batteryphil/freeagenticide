"""WebSocket session handler — wires AgentContext + Agent to a single WS connection.

Each WebSocket connection gets its own:
  - Session (conversation history)
  - AgentContext (shared cost/token accumulators)
  - Agent (root, depth=0)

The handler translates AgentChunk dataclasses into JSON ChunkMessages
and sends them to the React client in real time.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Coroutine, Optional

from fastapi import WebSocket, WebSocketDisconnect

from ag.core.agent import Agent
from ag.core.context import AgentChunk, AgentContext
from ag.core.session import Session
from ag.core.spawn import load_profile
from ag.providers.registry import ProviderRegistry
from ag.core.router import Router
from ag.tools.registry import ToolRegistry
from ag.core.config import Config
from ag.server.models import (
    ChunkMessage,
    DoneMessage,
    ErrorMessage,
    ProviderInfo,
    StatusMessage,
)


from ag.tools.ui_tools import WriteToEditorTool, RunInUITool


class WSSession:
    """Manages one WebSocket connection's full agent lifecycle."""

    def __init__(self, ws: WebSocket, cfg: Config) -> None:
        """Initialise a new session for a connected WebSocket client."""
        self._ws = ws
        self._cfg = cfg
        self._registry = ProviderRegistry(cfg.providers)
        self._router = Router(cfg.routing, self._registry)
        self._tools = ToolRegistry(cfg.tools)
        self._session = Session(context_token_limit=6000)
        self._context: Optional[AgentContext] = None
        self._agent: Optional[Agent] = None
        self._interrupt = asyncio.Event()

        # Inject UI-bridged tools — these need a reference to _send so they
        # can push editor_update / terminal_event messages to the browser.
        self._tools._tools["write_to_editor"] = WriteToEditorTool(self._ui_send)
        self._tools._tools["run_in_ui"] = RunInUITool(self._ui_send)

    def _ui_send(self, msg: dict) -> Coroutine[Any, Any, None]:
        """Return a coroutine that sends a UI message over the WebSocket.

        This is passed as a callback to UI tools so they can push
        editor/terminal events without holding a direct WS reference.

        Returns:
            Coroutine that sends the dict as JSON.
        """
        return self._send(msg)


    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Accept the WebSocket and enter the message receive loop."""
        await self._ws.accept()
        await self._send_status()

        try:
            while True:
                raw = await self._ws.receive_text()
                await self._handle_message(raw)
        except WebSocketDisconnect:
            pass

    # ── Incoming message dispatch ──────────────────────────────────────────────

    async def _handle_message(self, raw: str) -> None:
        """Route an incoming JSON message from the client."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await self._send(ErrorMessage(message="Invalid JSON from client"))
            return

        msg_type = data.get("type")
        if msg_type == "chat":
            await self._handle_chat(data.get("message", ""))
        elif msg_type == "interrupt":
            self._interrupt.set()
        else:
            await self._send(ErrorMessage(message=f"Unknown message type: {msg_type}"))

    async def _handle_chat(self, message: str) -> None:
        """Spin up / reuse the root agent and run the message loop."""
        if not message.strip():
            return

        self._interrupt.clear()

        # Re-resolve active model on every turn so UI model switches take effect
        from ag.server.model_manager import get_active_model
        active_model, active_provider_name = get_active_model()
        provider = self._registry.get(active_provider_name) or self._registry.get("ollama")

        # Lazy-init context — created once per WS connection
        if self._context is None:
            self._context = AgentContext(
                session_id="ws-session",
                registry=self._registry,
                router=self._router,
                tools=self._tools,
                output_callback=self._on_chunk,
            )

        # (Re-)create agent if not yet init'd or if model changed
        current_model = getattr(self._agent, "_model", None) if self._agent else None
        if self._agent is None or current_model != active_model:
            try:
                profile = load_profile("default")
                if active_model and hasattr(profile, "__dict__"):
                    profile = profile.__class__(**{**profile.__dict__, "model": active_model})

                self._agent = Agent(
                    profile=profile,
                    context=self._context,
                    provider=provider,
                    session=self._session,
                    tools=self._tools,
                    depth=0,
                )
                # Tag so we can detect changes next turn
                self._agent._model = active_model  # type: ignore[attr-defined]
            except Exception as exc:
                await self._send(ErrorMessage(message=f"Agent init failed: {exc}"))
                return

        try:
            await self._agent.message_loop(message)
        except asyncio.CancelledError:
            await self._send(ErrorMessage(
                message="Response interrupted.", recoverable=True
            ))
        except Exception as exc:
            await self._send(ErrorMessage(message=str(exc), recoverable=True))
        finally:
            cost = self._context.total_cost_usd if self._context else 0.0
            await self._send(DoneMessage(total_cost_usd=cost))
            await self._send_status()

    # ── AgentChunk → WebSocket ─────────────────────────────────────────────────

    def _on_chunk(self, chunk: AgentChunk) -> None:
        """Synchronous callback wired to AgentContext.output_callback.

        Schedules async send on the running event loop — safe to call
        from within the agent's async message loop since it runs in the
        same thread.
        """
        msg = ChunkMessage(
            text=chunk.text,
            agent_name=chunk.agent_name,
            depth=chunk.depth,
            is_tool_call=chunk.is_tool_call,
            is_tool_result=chunk.is_tool_result,
            is_final=chunk.is_final,
        )
        asyncio.ensure_future(self._send(msg))

    # ── Status broadcast ──────────────────────────────────────────────────────

    async def _send_status(self) -> None:
        """Send a provider health snapshot to the client."""
        try:
            health = await asyncio.wait_for(self._registry.check_all(), timeout=3.0)
        except asyncio.TimeoutError:
            health = {}

        providers = [
            ProviderInfo(
                name=name,
                available=h.available,
                latency_ms=h.latency_ms,
                model=h.models[0] if h.models else None,
            )
            for name, h in health.items()
        ]

        cost = self._context.total_cost_usd if self._context else 0.0
        tokens_in = self._context.tokens_in if self._context else 0
        tokens_out = self._context.tokens_out if self._context else 0

        await self._send(StatusMessage(
            providers=providers,
            total_cost_usd=cost,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        ))

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _send(self, msg: object) -> None:
        """Serialize and send a Pydantic model as JSON to the client."""
        try:
            if hasattr(msg, "model_dump_json"):
                await self._ws.send_text(msg.model_dump_json())
            else:
                await self._ws.send_text(json.dumps(msg))
        except Exception:
            pass  # Client disconnected mid-stream
