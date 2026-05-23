"""Project drill-down widget."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from rich.markup import escape
from textual.widgets import Static

from halyard.ai_log import AiSession, api_plus_tool_seconds
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
            f"Project: {escape(project)}",
            f"Sessions: {len(sessions)}",
            _budget_line(project, today_spend, month_spend),
            "",
            "Models",
        ]
        lines.extend(_model_lines(sessions))
        lines.extend(["", "Work Health"])
        lines.extend(_health_lines(sessions))
        lines.extend(["", "Recent Sessions"])
        for session in sessions[:12]:
            tokens = session.input_tokens + session.output_tokens
            err = f" ⚠{session.tool_errors}e" if session.tool_errors else ""
            surface = f" [{escape(session.client_surface)}]" if session.client_surface else ""
            lines.append(
                f"{tool_icon(session.tool)} "
                f"{escape(truncate(session.model, 18)):18} "
                f"{duration_str(session.end - session.start):>7} "
                f"{tokens:>8} tok "
                f"{cost_str(session.cost_usd):>9}"
                f"{surface}{err}"
            )
        # Most recent resume command, if any
        resume = next(
            (s.resume_command for s in sessions if s.resume_command),
            None,
        )
        if resume:
            lines.append(f"\nResume: {escape(resume)}")
        lines.append("")
        lines.append("Escape returns to feed")
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)


def _health_lines(sessions: list[AiSession]) -> list[str]:
    """Aggregate work-health signals across sessions. Signals, not scores."""
    rich = [
        s
        for s in sessions
        if s.tool_calls is not None
        or s.interaction_count is not None
        or s.files_touched_count is not None
        or s.test_status
        or s.build_status
    ]
    if not rich:
        return ["  No tool telemetry captured yet."]
    tool_rich = [s for s in rich if s.tool_calls is not None]
    total_calls = sum(s.tool_calls or 0 for s in tool_rich)
    total_errors = sum(s.tool_errors or 0 for s in tool_rich)
    error_rate = (total_errors / total_calls * 100) if total_calls else 0.0
    wall_list = [s.wall_seconds for s in sessions if s.wall_seconds is not None]
    avg_wall = sum(wall_list) / len(wall_list) if wall_list else None
    lines: list[str] = []
    if tool_rich:
        lines.append(
            f"  Tool calls:  {total_calls}  |  Errors: {total_errors}  ({error_rate:.0f}%)"
        )
    interaction_sessions = [s for s in sessions if s.interaction_count is not None]
    if interaction_sessions:
        interactions = sum(s.interaction_count or 0 for s in interaction_sessions)
        lines.append(f"  Interactions: {interactions} across {len(interaction_sessions)} sessions")
    unavailable = sum(1 for s in sessions if s.interaction_data_available is False)
    if unavailable:
        lines.append(f"  Interaction metadata unavailable: {unavailable} sessions")
    if avg_wall is not None:
        lines.append(f"  Avg wall time: {int(avg_wall)}s across {len(wall_list)} sessions")
    otel = [s for s in sessions if api_plus_tool_seconds(s) is not None]
    if otel:
        api_total = sum(s.api_seconds or 0 for s in otel)
        tool_total = sum(s.tool_seconds or 0 for s in otel)
        active_min = round((api_total + tool_total) / 60)
        lines.append(
            f"  Active {active_min}m (API {api_total}s · tool {tool_total}s) "
            f"across {len(otel)} sessions"
        )
    # Code delta — aggregate across sessions that have it
    added = sum(s.code_added for s in sessions if s.code_added is not None)
    removed = sum(s.code_removed for s in sessions if s.code_removed is not None)
    touched = sum(s.files_touched_count for s in sessions if s.files_touched_count is not None)
    if added or removed:
        lines.append(f"  Code delta:  +{added} / -{removed} lines")
    if touched:
        lines.append(f"  Files touched: {touched}")
    test_runs = sum(s.test_run_count or 0 for s in sessions if s.test_run_count is not None)
    passed = sum(1 for s in sessions if s.test_status == "pass")
    failed = sum(1 for s in sessions if s.test_status == "fail")
    if test_runs or passed or failed:
        lines.append(f"  Tests: {test_runs} runs  pass:{passed} fail:{failed}")
    return lines


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
        lines.append(
            f"{escape(truncate(model, 18)):18} {count:>3} {cost_str(cost):>9} {pct:>3}% {bar}"
        )
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
