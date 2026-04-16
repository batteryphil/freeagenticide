"""Streaming chat history panel widget — depth-aware multi-agent rendering."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from rich.markdown import Markdown
from rich.text import Text
from rich.panel import Panel
from rich.console import Group

from ag.core.context import AgentChunk

# Colour palette indexed by agent depth (depth 0 = root user-facing response)
_DEPTH_COLOURS = [
    "#1a6b3c",  # 0 root    — green
    "#1a4a6b",  # 1 level-1 — indigo
    "#5a3e8e",  # 2 level-2 — violet
    "#7a4a2e",  # 3 level-3 — amber-brown
]

_TOOL_CALL_STYLE = "dim italic"


def _depth_colour(depth: int) -> str:
    """Map nesting depth to a hex colour."""
    return _DEPTH_COLOURS[min(depth, len(_DEPTH_COLOURS) - 1)]


def _depth_indent(depth: int) -> str:
    """Return a visible indent string for sub-agent messages."""
    return "  " * depth


class ChatMessage(Static):
    """A single chat turn — user, root assistant, or sub-agent."""

    def __init__(
        self,
        role: str,
        content: str,
        provider: str = "",
        model: str = "",
        agent_name: str = "",
        depth: int = 0,
        is_tool_call: bool = False,
    ) -> None:
        """Initialise a chat message bubble."""
        super().__init__()
        self.role = role
        self.content = content
        self.provider = provider
        self.model = model
        self.agent_name = agent_name
        self.depth = depth
        self.is_tool_call = is_tool_call
        self._update_renderable()

    def _update_renderable(self) -> None:
        """Rebuild the rendered representation."""
        indent = _depth_indent(self.depth)
        colour = _depth_colour(self.depth)

        if self.role == "user":
            label = Text("  You  ", style="bold white on #5a3e8e")
            md = Markdown(self.content)
            self.update(Group(label, md))
            return

        if self.is_tool_call:
            # Tool calls / sub-agent announcements — dim, indented
            style = f"dim italic {colour}"
            txt = Text(f"{indent}{self.content}", style=style)
            self.update(txt)
            return

        # Assistant response — label shows depth + agent identity
        if self.depth == 0:
            tag_text = f" {self.provider}/{self.model} " if self.provider else " Assistant "
        else:
            tag_text = f" ↳ {self.agent_name} (depth {self.depth}) "

        label = Text(f"{indent}{tag_text}", style=f"bold white on {colour}")
        md = Markdown(indent + self.content) if self.content else Markdown("")
        self.update(Group(label, md))

    def append_text(self, text: str) -> None:
        """Append streamed text and re-render."""
        self.content += text
        self._update_renderable()


class ChatPanel(Widget):
    """Scrollable chat history panel — routes AgentChunks by depth."""

    DEFAULT_CSS = """
    ChatPanel {
        height: 1fr;
        overflow-y: auto;
        border: solid #2a2a3e;
        background: #0f0f1a;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Render empty panel initially."""
        yield Static(
            Text("  Antigravity-Local  ", style="bold white on #3a3a5e"),
            id="chat-header",
        )

    # ── Public message factories ───────────────────────────────────────────────

    def add_user_message(self, content: str) -> ChatMessage:
        """Append a user turn and return the widget."""
        msg = ChatMessage("user", content)
        self.mount(msg)
        self.scroll_end(animate=False)
        return msg

    def add_assistant_message(
        self,
        provider: str = "",
        model: str = "",
        agent_name: str = "",
        depth: int = 0,
    ) -> ChatMessage:
        """Append an empty assistant turn (to be streamed into)."""
        msg = ChatMessage(
            "assistant",
            "",
            provider=provider,
            model=model,
            agent_name=agent_name,
            depth=depth,
        )
        self.mount(msg)
        self.scroll_end(animate=False)
        return msg

    def add_tool_annotation(self, text: str, depth: int = 0) -> ChatMessage:
        """Append a dimmed tool-call / sub-agent announcement line."""
        msg = ChatMessage(
            "assistant",
            text,
            depth=depth,
            is_tool_call=True,
        )
        self.mount(msg)
        self.scroll_end(animate=False)
        return msg

    # ── Chunk router ──────────────────────────────────────────────────────────

    def route_chunk(
        self,
        chunk: AgentChunk,
        active_messages: dict[tuple[str, int], ChatMessage],
    ) -> None:
        """Route a streaming AgentChunk to the correct ChatMessage widget.

        `active_messages` is a dict keyed by (agent_name, depth) → ChatMessage.
        The caller (app.py) owns this dict and passes it here on each chunk.
        """
        key = (chunk.agent_name, chunk.depth)

        if chunk.is_tool_call or chunk.is_tool_result:
            # Tool-call annotations get their own ephemeral widget
            self.add_tool_annotation(chunk.text, depth=chunk.depth)
            return

        if key not in active_messages:
            # First chunk from this agent at this depth — open a new bubble
            msg = self.add_assistant_message(
                agent_name=chunk.agent_name,
                depth=chunk.depth,
            )
            active_messages[key] = msg

        active_messages[key].append_text(chunk.text)
        self.scroll_end(animate=False)
