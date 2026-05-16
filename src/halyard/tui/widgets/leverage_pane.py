"""Leverage widget — "is the AI spend producing shipped work?".

Same buckets as the web dashboard Leverage panel; both call
`leverage.summarize`, so the surfaces cannot diverge.
"""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.leverage import summarize


class LeveragePane(Static):
    """Render the shipped-rate rollup for the active TUI filter."""

    last_rendered_text = ""

    def render_sessions(self, sessions: list[AiSession], now: datetime | None = None) -> None:
        s = summarize(sessions, now or datetime.now())
        if s.total == 0:
            self.last_rendered_text = "⚑ Leverage\n\nNo sessions in the last 30 days."
            self.update(self.last_rendered_text)
            return

        lines = [
            "⚑ Leverage (30d)",
            "",
            f"Shipped {s.pct}%  ({s.merged} of {s.total} in merged PRs)",
            "",
            f"Merged   {s.merged:>3}",
            f"Open     {s.open_:>3}",
            f"Closed   {s.closed:>3}",
            f"No PR    {s.none:>3}",
            f"Unsynced {s.unsynced:>3}",
        ]
        if s.unsynced:
            lines.append("")
            lines.append("Run halyard outcome sync to resolve unsynced.")
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)
