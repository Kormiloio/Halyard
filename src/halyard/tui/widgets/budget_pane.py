"""Budget status widget."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Static

from halyard.budget import BudgetStatus, budget_status
from halyard.tui.formatters import budget_css_class, cost_str


class BudgetPane(Static):
    """Render spend against configured limits."""

    last_rendered_text = ""

    def render_budgets(self, now: datetime | None = None) -> None:
        statuses = budget_status(now=now)
        self.render_statuses(statuses)

    def render_statuses(self, statuses: list[BudgetStatus]) -> None:
        if not statuses:
            self.last_rendered_text = "Budget Status\n\nNo budgets set - run 'halyard set-budget'"
            self.update(self.last_rendered_text)
            return
        lines = ["Budget Status", ""]
        for status in statuses:
            day = _limit_text(status.today_spend, status.today_limit)
            month = _limit_text(status.month_spend, status.month_limit)
            css = budget_css_class(status.month_spend, status.month_limit)
            lines.append(f"{status.slug} [{css}]today {day} month {month}[/{css}]")
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)


def _limit_text(spend: float, limit: float | None) -> str:
    if limit is None:
        return f"{cost_str(spend)} / -"
    return f"{cost_str(spend)} / {cost_str(limit)}"
