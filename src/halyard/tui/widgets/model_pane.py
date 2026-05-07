"""Model breakdown widget."""

from __future__ import annotations

from collections import defaultdict

from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.tui.formatters import cost_str, truncate


class ModelPane(Static):
    """Render cost by model."""

    def render_sessions(self, sessions: list[AiSession]) -> None:
        totals: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        for session in sessions:
            count, cost = totals[session.model]
            totals[session.model] = (count + 1, cost + session.cost_usd)

        if not totals:
            self.update("Model Breakdown\n\nNo model spend.")
            return

        total_cost = sum(cost for _count, cost in totals.values())
        lines = ["Model Breakdown", ""]
        sorted_totals = sorted(totals.items(), key=lambda item: item[1][1], reverse=True)
        for model, (count, cost) in sorted_totals:
            pct = 0 if total_cost <= 0 else int((cost / total_cost) * 100)
            bar = "#" * max(1, min(20, pct // 5)) if cost > 0 else "-"
            lines.append(f"{truncate(model, 18):18} {count:>3} {cost_str(cost):>9} {pct:>3}% {bar}")
        self.update("\n".join(lines))
