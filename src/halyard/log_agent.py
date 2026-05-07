"""Provider-neutral query layer for `halyard log`."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from halyard.ai_log import AiSession, parse_sessions
from halyard.reports import format_minutes, parse_timeclock, summarize_ai_sessions

LogAgent = Literal["local", "claude"]


@dataclass(frozen=True)
class LogBucket:
    label: str
    cost_usd: float
    sessions: int


@dataclass(frozen=True)
class LogQueryFilters:
    tool: str | None = None
    project: str | None = None
    model: str | None = None
    branch: str | None = None


@dataclass(frozen=True)
class LogQueryResponse:
    answer: str
    query: str
    agent: LogAgent
    data_source: str
    period: str
    cost_usd_total: float
    session_count: int
    human_minutes: int
    filters: LogQueryFilters
    projects: list[LogBucket]
    models: list[LogBucket]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class LogAgentError(Exception):
    """Raised when a requested log query provider cannot answer."""


def run_log_query(
    query: str,
    *,
    project_dir: Path,
    agent: LogAgent = "local",
    period: str = "month",
    model: str | None = None,
    filters: LogQueryFilters | None = None,
    now: datetime | None = None,
) -> LogQueryResponse:
    """Run a query through the selected provider."""
    if agent == "local":
        return run_local_log_query(
            query, project_dir=project_dir, period=period, filters=filters, now=now
        )
    if agent == "claude":
        raise LogAgentError(
            "--agent claude is not implemented yet. Use --agent local for offline log queries."
        )
    raise LogAgentError(f"Unknown log agent: {agent}")


def run_local_log_query(
    query: str,
    *,
    project_dir: Path,
    period: str = "month",
    filters: LogQueryFilters | None = None,
    now: datetime | None = None,
) -> LogQueryResponse:
    """Answer from local Halyard metadata only, without network access."""
    clock = now or datetime.now()
    inferred_period = _infer_period(query) if period == "month" else None
    effective_period = inferred_period or period
    effective_filters = _merge_filters(_infer_filters(query), filters)
    sessions = _filter_sessions_for_period(parse_sessions(project_dir), effective_period, clock)
    sessions = _filter_sessions(sessions, effective_filters)
    report_data = summarize_ai_sessions(sessions, period_label=effective_period)
    time_entries = _filter_time_entries_for_period(
        parse_timeclock(project_dir / "time.timeclock", now=clock), effective_period, clock
    )
    human_minutes = sum(
        max(0, int((end - start).total_seconds() // 60)) for start, end, _ in time_entries
    )

    return LogQueryResponse(
        answer=(
            f"{effective_period.title()} captured {len(sessions)} AI session(s), "
            f"${report_data.total_cost:.2f} AI cost, and "
            f"{format_minutes(human_minutes)} human time."
        ),
        query=query,
        agent="local",
        data_source=str(project_dir),
        period=effective_period,
        cost_usd_total=round(report_data.total_cost, 4),
        session_count=len(sessions),
        human_minutes=human_minutes,
        filters=effective_filters,
        projects=[
            LogBucket(
                label=bucket.label,
                cost_usd=round(bucket.cost_usd, 4),
                sessions=bucket.sessions,
            )
            for bucket in report_data.by_project
        ],
        models=[
            LogBucket(
                label=bucket.label,
                cost_usd=round(bucket.cost_usd, 4),
                sessions=bucket.sessions,
            )
            for bucket in report_data.by_model
        ],
    )


def _merge_filters(inferred: LogQueryFilters, explicit: LogQueryFilters | None) -> LogQueryFilters:
    if explicit is None:
        return inferred
    return LogQueryFilters(
        tool=explicit.tool or inferred.tool,
        project=explicit.project or inferred.project,
        model=explicit.model or inferred.model,
        branch=explicit.branch or inferred.branch,
    )


def _infer_period(query: str) -> str | None:
    q = query.lower()
    if "all time" in q or "all-time" in q:
        return "all"
    if "today" in q:
        return "today"
    if "this week" in q or "week" in q:
        return "week"
    if "this month" in q or "month" in q:
        return "month"
    return None


def _infer_filters(query: str) -> LogQueryFilters:
    q = query.lower()
    return LogQueryFilters(
        tool=_infer_tool(q),
        project=_infer_project(q),
        model=_infer_model(q),
        branch=_infer_branch(q),
    )


def _infer_tool(query: str) -> str | None:
    tool_aliases = {
        "cursor": "cursor",
        "claude code": "claude-code",
        "claude-code": "claude-code",
        "claude": "claude-code",
        "gemini cli": "gemini-cli",
        "gemini-cli": "gemini-cli",
        "gemini": "gemini-cli",
        "codex": "codex",
    }
    for alias, tool in tool_aliases.items():
        if alias in query:
            return tool
    return None


def _infer_project(query: str) -> str | None:
    for raw in query.replace(",", " ").split():
        token = raw.strip("?!'\"()[]{}")
        if ":" in token and "/" not in token:
            return token
        if "/" in token and not token.startswith(("http://", "https://")):
            left, right = token.split("/", 1)
            if left and right:
                return f"{left}:{right}"
    return None


def _infer_model(query: str) -> str | None:
    for marker in ("model ", "using "):
        if marker in query:
            tail = query.split(marker, 1)[1].strip()
            return tail.split()[0].strip("?!'\"()[]{}") if tail else None
    return None


def _infer_branch(query: str) -> str | None:
    for marker in ("branch ", "on branch ", "on "):
        if marker in query:
            tail = query.split(marker, 1)[1].strip()
            return tail.split()[0].strip("?!'\"()[]{}") if tail else None
    return None


def _filter_sessions(sessions: list[AiSession], filters: LogQueryFilters) -> list[AiSession]:
    result = sessions
    if filters.tool:
        result = [session for session in result if session.tool == filters.tool]
    if filters.project:
        result = [session for session in result if session.project == filters.project]
    if filters.model:
        model = filters.model.lower()
        result = [session for session in result if model in session.model.lower()]
    if filters.branch:
        branch_tag = f"branch:{filters.branch}"
        result = [session for session in result if branch_tag in session.tags]
    return result


def _filter_sessions_for_period(
    sessions: list[AiSession], period: str, now: datetime
) -> list[AiSession]:
    period = period.lower()
    if period == "all":
        return sessions
    if period == "today":
        return [session for session in sessions if session.start.date() == now.date()]
    if period == "week":
        start = now - timedelta(days=now.weekday())
        return [session for session in sessions if session.start.date() >= start.date()]
    if period == "month":
        return [
            session
            for session in sessions
            if session.start.year == now.year and session.start.month == now.month
        ]
    raise LogAgentError("period must be one of: today, week, month, all")


def _filter_time_entries_for_period(
    entries: list[tuple[datetime, datetime, str]],
    period: str,
    now: datetime,
) -> list[tuple[datetime, datetime, str]]:
    period = period.lower()
    if period == "all":
        return entries
    if period == "today":
        return [entry for entry in entries if entry[0].date() == now.date()]
    if period == "week":
        start = now - timedelta(days=now.weekday())
        return [entry for entry in entries if entry[0].date() >= start.date()]
    if period == "month":
        return [
            entry for entry in entries if entry[0].year == now.year and entry[0].month == now.month
        ]
    raise LogAgentError("period must be one of: today, week, month, all")
