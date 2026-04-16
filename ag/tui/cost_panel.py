"""Cost and token tracker panel — right sidebar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static
from rich.table import Table
from rich.text import Text


class CostPanel(Widget):
    """Right sidebar tracking tokens, cost, and routing decisions."""

    DEFAULT_CSS = """
    CostPanel {
        width: 28;
        border: solid #2a2a3e;
        background: #0a0a14;
        padding: 1;
    }
    .cost-section {
        color: #9999dd;
        text-style: bold;
        margin: 1 0 0 0;
    }
    #routing-log {
        color: #8888cc;
        margin: 0 0 0 0;
        overflow-y: auto;
        height: 1fr;
    }
    """

    def __init__(self) -> None:
        """Initialise with zero counters."""
        super().__init__()
        self._tokens_in: int = 0
        self._tokens_out: int = 0
        self._cost_usd: float = 0.0
        self._routing_log: list[str] = []
        self._budget_limit: float = 5.00

    def compose(self) -> ComposeResult:
        """Build the cost panel layout."""
        yield Static("💰 Session Cost", classes="cost-section")
        yield Static("", id="cost-stats")
        yield Static("─" * 24, classes="cost-section")
        yield Static("🔀 Routing", classes="cost-section")
        yield Static("", id="routing-log")

    def set_budget(self, limit: float) -> None:
        """Set the budget limit for display purposes."""
        self._budget_limit = limit

    def record_usage(
        self,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        provider: str,
        model: str,
        reason: str,
        complexity: float,
    ) -> None:
        """Add a completed turn's usage to the running totals."""
        self._tokens_in += tokens_in
        self._tokens_out += tokens_out
        self._cost_usd += cost_usd
        self._routing_log.insert(
            0,
            f"[{reason[:12]}] {provider}/{model[:12]}\n"
            f"  complexity={complexity:.2f}  ${cost_usd:.4f}",
        )
        if len(self._routing_log) > 20:
            self._routing_log = self._routing_log[:20]
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Re-render the stats and routing log widgets."""
        budget_pct = min(1.0, self._cost_usd / max(self._budget_limit, 0.001))
        bar_len = 20
        filled = int(bar_len * budget_pct)
        bar_color = "green" if budget_pct < 0.6 else ("yellow" if budget_pct < 0.9 else "red")
        bar = f"[{bar_color}]{'█' * filled}{'░' * (bar_len - filled)}[/]"

        stats = (
            f"In:   {self._tokens_in:,} tok\n"
            f"Out:  {self._tokens_out:,} tok\n"
            f"Cost: ${self._cost_usd:.4f}\n"
            f"Limit: ${self._budget_limit:.2f}\n"
            f"{bar}"
        )
        self.query_one("#cost-stats", Static).update(stats)

        log_text = "\n\n".join(self._routing_log[:8]) or "(no calls yet)"
        self.query_one("#routing-log", Static).update(log_text)
