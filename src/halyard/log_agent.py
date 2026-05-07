"""Provider-neutral query layer for `halyard log`."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from halyard.ai_log import AiSession, parse_sessions
from halyard.reports import (
    format_minutes,
    parse_timeclock,
    summarize_ai_sessions,
)

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


# ---------------------------------------------------------------------------
# Anthropic Tool Schemas
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_sessions",
        "description": "Read individual AI work sessions from the log, with optional filters.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                "tool": {
                    "type": "string",
                    "description": "Filter by tool name (cursor, codex, etc.)",
                },
                "project": {
                    "type": "string",
                    "description": "Filter by project slug (client:project)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max sessions to return",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "summarize_by_project",
        "description": "Get aggregated costs and session counts grouped by project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
            },
        },
    },
    {
        "name": "summarize_by_model",
        "description": "Get aggregated costs and session counts grouped by AI model.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
            },
        },
    },
    {
        "name": "read_timeclock",
        "description": "Read human time entries from the timeclock file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "ISO date (YYYY-MM-DD)"},
            },
        },
    },
]


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
        return run_claude_log_query(
            query,
            project_dir=project_dir,
            model=model or "claude-3-5-sonnet-20241022",
            now=now,
        )
    raise LogAgentError(f"Unknown log agent: {agent}")


def run_claude_log_query(
    query: str,
    *,
    project_dir: Path,
    model: str,
    now: datetime | None = None,
) -> LogQueryResponse:
    """Answer via Anthropic SDK using tool-use for local data retrieval."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LogAgentError(
            "Missing ANTHROPIC_API_KEY environment variable. "
            "Set it to use the --agent claude provider."
        )

    clock = now or datetime.now()
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = (
        f"You are the Halyard AI Assistant. Today is {clock.strftime('%Y-%m-%d %A')}. "
        "Your role is to answer questions about the user's work sessions and costs. "
        "Use the provided tools to fetch data from the local Halyard logs. "
        "Never make up data; if tools return no results, say so. "
        "When summarizing costs, use the USD totals from the tools."
    )

    messages: list[Any] = [{"role": "user", "content": query}]
    captured_buckets_project: list[LogBucket] = []
    captured_buckets_model: list[LogBucket] = []
    total_cost = 0.0
    session_count = 0
    human_minutes = 0

    try:
        # Max 3 turns to prevent runaway loops
        for _ in range(3):
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                system=system_prompt,
                tools=_TOOLS,  # type: ignore[arg-type]
                messages=messages,
            )

            if response.stop_reason != "tool_use":
                # Final answer reached
                text_content = next(
                    (c.text for c in response.content if hasattr(c, "text")),
                    "(No answer provided)",
                )
                return LogQueryResponse(
                    answer=text_content,
                    query=query,
                    agent="claude",
                    data_source=str(project_dir),
                    period="dynamic",
                    cost_usd_total=round(total_cost, 4),
                    session_count=session_count,
                    human_minutes=human_minutes,
                    filters=LogQueryFilters(),
                    projects=captured_buckets_project,
                    models=captured_buckets_model,
                )

            # Process tool calls
            messages.append({"role": "assistant", "content": response.content})
            for content in response.content:
                if content.type == "tool_use":
                    tool_name = content.name
                    tool_args = content.input
                    tool_result = _execute_tool(tool_name, tool_args, project_dir, clock)

                    # Update internal counters if it was a summary tool
                    if isinstance(tool_result, dict):
                        if "total_cost" in tool_result:
                            total_cost = max(total_cost, tool_result.get("total_cost", 0.0))
                            session_count = max(session_count, tool_result.get("session_count", 0))
                        if "by_project" in tool_result:
                            captured_buckets_project = [
                                LogBucket(
                                    label=b["label"],
                                    cost_usd=b["cost_usd"],
                                    sessions=b["sessions"],
                                )
                                for b in tool_result["by_project"]
                            ]
                        if "by_model" in tool_result:
                            captured_buckets_model = [
                                LogBucket(
                                    label=b["label"],
                                    cost_usd=b["cost_usd"],
                                    sessions=b["sessions"],
                                )
                                for b in tool_result["by_model"]
                            ]
                        if "total_minutes" in tool_result:
                            human_minutes = max(human_minutes, tool_result["total_minutes"])

                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": content.id,
                                    "content": json.dumps(tool_result),
                                }
                            ],
                        }
                    )

        raise LogAgentError("Agent exceeded maximum turn limit (3) without a final answer.")

    except anthropic.AnthropicError as exc:
        raise LogAgentError(f"Anthropic API error: {exc}") from exc


def _execute_tool(name: str, args: dict[str, Any], project_dir: Path, now: datetime) -> Any:
    """Route a tool call to the local Halyard data layer."""
    start_date = _parse_date(args.get("start_date"))
    end_date = _parse_date(args.get("end_date"))

    if name == "read_sessions":
        sessions = parse_sessions(project_dir)
        sessions = _filter_sessions_by_date(sessions, start_date, end_date)
        if tool := args.get("tool"):
            sessions = [s for s in sessions if s.tool == tool]
        if project := args.get("project"):
            sessions = [s for s in sessions if s.project == project]
        limit = args.get("limit", 20)
        return [asdict(s) for s in sessions[:limit]]

    if name == "summarize_by_project" or name == "summarize_by_model":
        sessions = parse_sessions(project_dir)
        sessions = _filter_sessions_by_date(sessions, start_date, end_date)
        report = summarize_ai_sessions(sessions, period_label="agent-query")
        return {
            "total_cost": round(report.total_cost, 4),
            "session_count": len(sessions),
            "by_project": [
                {"label": b.label, "cost_usd": round(b.cost_usd, 4), "sessions": b.sessions}
                for b in report.by_project
            ],
            "by_model": [
                {"label": b.label, "cost_usd": round(b.cost_usd, 4), "sessions": b.sessions}
                for b in report.by_model
            ],
        }

    if name == "read_timeclock":
        entries = parse_timeclock(project_dir / "time.timeclock", now=now)
        filtered = []
        total_minutes = 0
        for start, end, note in entries:
            if start_date and start.date() < start_date:
                continue
            if end_date and start.date() > end_date:
                continue
            filtered.append(
                {"start": start.isoformat(), "end": end.isoformat(), "note": note}
            )
            total_minutes += max(0, int((end - start).total_seconds() // 60))
        return {"total_minutes": total_minutes, "entries": filtered[:50]}

    return {"error": f"Unknown tool: {name}"}


def _parse_date(d: str | None) -> Any:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d).date()
    except ValueError:
        return None


def _filter_sessions_by_date(
    sessions: list[AiSession], start: Any | None, end: Any | None
) -> list[AiSession]:
    result = sessions
    if start:
        result = [s for s in result if s.start.date() >= start]
    if end:
        result = [s for s in result if s.start.date() <= end]
    return result


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
