"""Project drill-down widget."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.budget import load_budgets
from halyard.tui.formatters import budget_css_class, cost_str, duration_str, tool_icon, truncate


class ProjectPane(Static):
    """Render detail for one project."""

    last_rendered_text = ""

    def render_project(
        self,
        project: str,
        sessions: list[AiSession],
        now: datetime | None = None,
    ) -> None:
        clock = now or datetime.now()
        today_spend = sum(s.cost_usd for s in sessions if s.start.date() == clock.date())
        month_spend = sum(
            s.cost_usd
            for s in sessions
            if s.start.year == clock.year and s.start.month == clock.month
        )

        lines = [
            f"Project: {project}",
            f"Sessions: {len(sessions)}",
            _budget_line(project, today_spend, month_spend),
            "",
            "Models",
        ]
        lines.extend(_model_lines(sessions))
        lines.extend(["", "Recent Sessions"])
        for session in sessions[:12]:
            tokens = session.input_tokens + session.output_tokens
            lines.append(
                f"{tool_icon(session.tool)} "
                f"{truncate(session.model, 18):18} "
                f"{duration_str(session.end - session.start):>7} "
                f"{tokens:>8} tok "
                f"{cost_str(session.cost_usd):>9}"
            )
        lines.append("")
        lines.append("Escape returns to feed")
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)


def _model_lines(sessions: list[AiSession]) -> list[str]:
    totals: dict[str, tuple[int, float]] = defaultdict(lambda: (0, 0.0))
    for session in sessions:
        count, cost = totals[session.model]
        totals[session.model] = (count + 1, cost + session.cost_usd)

    if not totals:
        return ["No model spend."]

    total_cost = sum(cost for _count, cost in totals.values())
    lines: list[str] = []
    sorted_totals = sorted(totals.items(), key=lambda item: item[1][1], reverse=True)
    for model, (count, cost) in sorted_totals:
        pct = 0 if total_cost <= 0 else int((cost / total_cost) * 100)
        bar = "#" * max(1, min(20, pct // 5)) if cost > 0 else "-"
        lines.append(f"{truncate(model, 18):18} {count:>3} {cost_str(cost):>9} {pct:>3}% {bar}")
    return lines


def _budget_line(project: str, today_spend: float, month_spend: float) -> str:
    budget = load_budgets().get(project)
    if budget is None:
        return f"Today: {cost_str(today_spend)} / -  Month: {cost_str(month_spend)} / -"
    day = _limit_text(today_spend, budget.daily_usd)
    month = _limit_text(month_spend, budget.monthly_usd)
    day_class = budget_css_class(today_spend, budget.daily_usd)
    month_class = budget_css_class(month_spend, budget.monthly_usd)
    return f"Today: [{day_class}]{day}[/{day_class}]  Month: [{month_class}]{month}[/{month_class}]"


def _limit_text(spend: float, limit: float | None) -> str:
    if limit is None:
        return f"{cost_str(spend)} / -"
    return f"{cost_str(spend)} / {cost_str(limit)}"
