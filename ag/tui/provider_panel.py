"""Provider status sidebar — shows health and lets user pick provider/model."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label, Select, Static
from textual.reactive import reactive
from rich.text import Text

from ag.providers.base import ProviderHealth


class ProviderPanel(Widget):
    """Left sidebar for provider selection and health status."""

    DEFAULT_CSS = """
    ProviderPanel {
        width: 26;
        border: solid #2a2a3e;
        background: #0a0a14;
        padding: 1;
    }
    ProviderPanel Label {
        color: #8888cc;
        margin: 0 0 0 0;
    }
    ProviderPanel Select {
        margin: 0 0 1 0;
    }
    .health-row {
        margin: 0 0 0 0;
        color: #aaaacc;
    }
    .health-available {
        color: #44ff88;
    }
    .health-unavailable {
        color: #ff4444;
    }
    .section-title {
        color: #9999dd;
        text-style: bold;
        margin: 1 0 0 0;
    }
    """

    current_provider: reactive[str] = reactive("ollama")
    current_model: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        """Build the sidebar layout."""
        yield Static("⚡ Antigravity", classes="section-title", id="sidebar-title")
        yield Label("Provider")
        yield Select(
            [("ollama (local)", "ollama")],
            id="provider-select",
            value="ollama",
        )
        yield Label("Model")
        yield Select(
            [("llama3.2:3b", "llama3.2:3b")],
            id="model-select",
            value="llama3.2:3b",
        )
        yield Static("─" * 22, classes="section-title")
        yield Static("Health", classes="section-title")
        yield Static("Checking...", id="health-status")

    def update_health(self, health: dict[str, ProviderHealth]) -> None:
        """Refresh the health display and repopulate provider selector."""
        lines: list[str] = []
        provider_options: list[tuple[str, str]] = []

        for name, h in sorted(health.items()):
            icon = "🟢" if h.available else "🔴"
            latency = f" {h.latency_ms:.0f}ms" if h.available else ""
            lines.append(f"{icon} {name}{latency}")
            if h.available:
                label = f"{name} {'(local)' if name == 'ollama' else '(cloud)'}"
                provider_options.append((label, name))

        status_widget = self.query_one("#health-status", Static)
        status_widget.update("\n".join(lines) or "No providers")

        if provider_options:
            current = self.current_provider
            # Determine value to restore — keep current if still available.
            new_value = current if any(v == current for _, v in provider_options) else provider_options[0][1]
            self._replace_select("provider-select", provider_options, new_value)

    def update_models(self, models: list[str]) -> None:
        """Update the model selector for the chosen provider."""
        options = [(m, m) for m in models] if models else [("(none)", "")]
        new_value = options[0][1]
        self._replace_select("model-select", options, new_value)
        self.current_model = new_value

    def _replace_select(
        self,
        widget_id: str,
        options: list[tuple[str, str]],
        value: str,
    ) -> None:
        """Remove the existing Select widget and mount a fresh one with *options*.

        Textual has no public set_options() API. The correct pattern is to
        remove the old Select and mount a new one. We capture the insertion
        anchor *before* the remove() call, then defer the mount via
        call_after_refresh so Textual's layout engine sees a settled DOM.
        """
        anchor = self.query_one("#health-status", Static)
        old = self.query_one(f"#{widget_id}", Select)
        old.remove()
        new_select = Select(options, id=widget_id, value=value)
        self.call_after_refresh(self.mount, new_select, before=anchor)

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle provider or model selection changes."""
        if event.select.id == "provider-select":
            self.current_provider = str(event.value)
            self.post_message(ProviderChanged(str(event.value)))
        elif event.select.id == "model-select":
            self.current_model = str(event.value)


class ProviderChanged(Message):
    """Posted when the user selects a new provider."""

    def __init__(self, provider: str) -> None:
        """Initialise with selected provider name."""
        super().__init__()
        self.provider = provider
