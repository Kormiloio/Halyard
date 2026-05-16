"""Read-only MCP server over the local Halyard ledger.

Exposes the aggregate ledger (every registered project + hub, deduped)
to MCP clients (Claude Code, Cursor, …) so the agent can ask about its
own AI work. Read-only: no tool writes, deletes, or mutates anything;
only metadata already in the plain-text ledger is returned (never
prompts, code, or transcripts).

The `mcp` SDK is an optional dependency; it is imported lazily inside
``build_server`` so importing this module (and the helpers tests use)
never requires it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from halyard.ai_log import AiSession, parse_sessions
from halyard.reports import _dedup_sessions, aggregate_session_dirs
from halyard.usage import round_money, sum_spend

Period = str  # "7d" | "30d" | "month" | "all"


def _aggregate_sessions() -> list[AiSession]:
    merged: list[AiSession] = []
    for d in aggregate_session_dirs():
        merged.extend(parse_sessions(d))
    return _dedup_sessions(merged)


def _window(period: Period, now: datetime | None = None) -> tuple[datetime, datetime, str]:
    clock = now or datetime.now()
    if period == "7d":
        return clock - timedelta(days=7), clock, "last 7 days"
    if period == "month":
        return datetime(clock.year, clock.month, 1), clock, clock.strftime("%B %Y")
    if period == "all":
        return datetime(1970, 1, 1), clock, "all time"
    return clock - timedelta(days=30), clock, "last 30 days"


def _in_window(s: AiSession, start: datetime, end: datetime) -> bool:
    return start <= s.end <= end


def _attribution_mix_block(sessions: list[AiSession]) -> dict[str, int]:
    """Per-confidence session counts (timer/mapped/toml/auto/unknown/none)."""
    from halyard.attribution import attribution_mix

    return {str(k): v for k, v in attribution_mix(sessions).items()}


def _work_summary(period: Period = "30d") -> dict[str, Any]:
    start, end, label = _window(period)
    sessions = [s for s in _aggregate_sessions() if _in_window(s, start, end)]
    by_tool: dict[str, int] = {}
    by_project: dict[str, float] = {}
    for s in sessions:
        by_tool[s.tool] = by_tool.get(s.tool, 0) + 1
        if s.project:
            by_project[s.project] = by_project.get(s.project, 0.0) + s.cost_usd
    adrift = sum(1 for s in sessions if not s.project)
    n = len(sessions)
    top = sorted(by_project.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "period": label,
        "sessions": n,
        "total_cost_usd": round_money(sum(s.cost_usd for s in sessions)),
        "by_tool": dict(sorted(by_tool.items(), key=lambda kv: kv[1], reverse=True)),
        "top_projects": [{"project": p, "cost_usd": round_money(c)} for p, c in top],
        "adrift_sessions": adrift,
        "adrift_pct": round(100 * adrift / n, 1) if n else 0.0,
        "attribution_mix": _attribution_mix_block(sessions),
        "outcomes": _outcomes_status(period),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _sessions(
    limit: int = 20,
    project: str | None = None,
    tool: str | None = None,
    since: str | None = None,
) -> list[dict[str, Any]]:
    cutoff: datetime | None = None
    if since:
        try:
            cutoff = datetime.fromisoformat(since)
        except ValueError:
            cutoff = None
    out = []
    for s in sorted(_aggregate_sessions(), key=lambda x: x.end, reverse=True):
        if project and s.project != project:
            continue
        if tool and s.tool != tool:
            continue
        if cutoff and s.end < cutoff:
            continue
        out.append(
            {
                "start": s.start.isoformat(timespec="seconds"),
                "end": s.end.isoformat(timespec="seconds"),
                "tool": s.tool,
                "model": s.model,
                "input_tokens": s.input_tokens,
                "output_tokens": s.output_tokens,
                "cost_usd": round_money(s.cost_usd),
                "project": s.project,
                "branch": s.branch,
            }
        )
        if len(out) >= max(1, min(limit, 200)):
            break
    return out


def _spend_in_range(
    start: str,
    end: str,
    api_only: bool = True,
    project: str | None = None,
) -> dict[str, Any]:
    ps = datetime.fromisoformat(start)
    pe = datetime.fromisoformat(end)
    sessions = _aggregate_sessions()
    accounts = {project} if project else None
    usd = sum_spend(sessions, period_start=ps, period_end=pe, api_only=api_only, accounts=accounts)
    n = sum(
        1
        for s in sessions
        if ps <= s.end < pe
        and (not api_only or (s.billing == "api" and s.cost_usd > 0))
        and (accounts is None or s.project in accounts)
    )
    return {"usd": usd, "sessions": n, "start": start, "end": end, "api_only": api_only}


def _project_breakdown(period: Period = "30d") -> list[dict[str, Any]]:
    start, end, _ = _window(period)
    agg: dict[str, dict[str, float]] = {}
    for s in _aggregate_sessions():
        if not _in_window(s, start, end):
            continue
        key = s.project or "(unattributed)"
        e = agg.setdefault(key, {"sessions": 0, "cost": 0.0})
        e["sessions"] += 1
        e["cost"] += s.cost_usd
    return [
        {"project": k, "sessions": int(v["sessions"]), "cost_usd": round_money(v["cost"])}
        for k, v in sorted(agg.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    ]


def _cost_by_model(period: Period = "30d") -> list[dict[str, Any]]:
    from halyard.model_breakdown import iter_model_usage
    from halyard.model_breakdown import parse as _parse_breakdown

    start, end, _ = _window(period)
    agg: dict[str, dict[str, float]] = {}
    for s in _aggregate_sessions():
        if not _in_window(s, start, end):
            continue
        if _parse_breakdown(s.model_breakdown) is not None:
            for model, m_in, m_out, _cr, _cw, m_cost in iter_model_usage(s):
                e = agg.setdefault(model, {"sessions": 0, "tokens": 0, "cost": 0.0})
                e["sessions"] += 1
                e["tokens"] += m_in + m_out
                e["cost"] += m_cost
            continue
        e = agg.setdefault(s.model, {"sessions": 0, "tokens": 0, "cost": 0.0})
        e["sessions"] += 1
        e["tokens"] += s.input_tokens + s.output_tokens
        e["cost"] += s.cost_usd
    return [
        {
            "model": k,
            "sessions": int(v["sessions"]),
            "tokens": int(v["tokens"]),
            "cost_usd": round_money(v["cost"]),
        }
        for k, v in sorted(agg.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    ]


def _outcomes_status(period: Period = "30d") -> dict[str, int]:
    start, end, _ = _window(period)
    counts = {"merged": 0, "open": 0, "closed": 0, "none": 0, "not_synced": 0}
    for s in _aggregate_sessions():
        if not _in_window(s, start, end):
            continue
        st = s.pr_state
        if st in ("merged", "open", "closed", "none"):
            counts[st] += 1
        else:
            counts["not_synced"] += 1
    return counts


def build_server() -> Any:
    """Construct the FastMCP server (lazy import keeps the SDK optional)."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("halyard")

    @mcp.tool()
    def work_summary(period: str = "30d") -> dict[str, Any]:
        """One-call rollup of AI work for a period.

        period: "7d" | "30d" | "month" | "all". Returns session count,
        total USD cost, sessions by tool, top projects by cost,
        unattributed ("adrift") count and %, and PR outcome counts.
        """
        return _work_summary(period)

    @mcp.tool()
    def sessions(
        limit: int = 20,
        project: str | None = None,
        tool: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Most recent AI sessions (newest first), filterable.

        project/tool filter exactly; since is an ISO datetime lower
        bound on session end. Returns metadata only (no prompts/code).
        """
        return _sessions(limit, project, tool, since)

    @mcp.tool()
    def spend_in_range(
        start: str, end: str, api_only: bool = True, project: str | None = None
    ) -> dict[str, Any]:
        """Total spend in [start, end) (ISO datetimes), half-open on
        session end. api_only counts only billed API sessions."""
        return _spend_in_range(start, end, api_only, project)

    @mcp.tool()
    def project_breakdown(period: str = "30d") -> list[dict[str, Any]]:
        """Sessions and cost per project for the period, cost-desc."""
        return _project_breakdown(period)

    @mcp.tool()
    def cost_by_model(period: str = "30d") -> list[dict[str, Any]]:
        """Sessions, tokens and cost per model for the period."""
        return _cost_by_model(period)

    @mcp.tool()
    def outcomes_status(period: str = "30d") -> dict[str, int]:
        """PR outcome counts (merged/open/closed/none/not_synced)."""
        return _outcomes_status(period)

    return mcp
