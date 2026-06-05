"""Shared leverage calc — the single source for "did the AI work ship?".

The web dashboard's `_leverage_panel` and the TUI `LeveragePane` both
derive their numbers from `summarize()`, so the two surfaces can never
disagree. Pure read over `pr_state` Halyard already captures; no writes,
no new fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from halyard.ai_log import AiSession
from halyard.mcp_inventory import MCP_SERVER_ALLOWLIST

LEVERAGE_WINDOW_DAYS = 30


def humanize_seconds(secs: int) -> str:
    """Compact human duration: '45m', '3h 12m', '2d 4h'. Integers only."""
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        h, rem = divmod(secs, 3600)
        m = rem // 60
        return f"{h}h {m}m" if m else f"{h}h"
    d, rem = divmod(secs, 86400)
    h = rem // 3600
    return f"{d}d {h}h" if h else f"{d}d"


def _median_int(values: list[int]) -> int | None:
    return round(median(values)) if values else None


@dataclass(frozen=True)
class LeverageSummary:
    total: int
    merged: int
    open_: int
    closed: int
    none: int
    unsynced: int
    pct: int
    # v3.1 review-friction medians over the window (None when no data).
    median_time_to_merge_s: int | None = None
    median_review_comments: int | None = None


def summarize(sessions: list[AiSession], now: datetime) -> LeverageSummary:
    """Engineering-outcome rollup over the trailing 30 days.

    ``pct`` is merged / total as an int; ``unsynced`` counts sessions
    whose ``pr_state`` has not been resolved yet (falsy state).
    """
    cutoff = now - timedelta(days=LEVERAGE_WINDOW_DAYS)
    recent = [s for s in sessions if s.start >= cutoff]
    total = len(recent)
    merged = sum(1 for s in recent if s.pr_state == "merged")
    open_ = sum(1 for s in recent if s.pr_state == "open")
    closed = sum(1 for s in recent if s.pr_state == "closed")
    none = sum(1 for s in recent if s.pr_state == "none")
    unsynced = sum(1 for s in recent if not s.pr_state)
    pct = int((merged / total) * 100) if total else 0
    ttm = [s.time_to_merge_s for s in recent if s.time_to_merge_s is not None]
    rc = [s.review_comments for s in recent if s.review_comments is not None]
    return LeverageSummary(
        total=total,
        merged=merged,
        open_=open_,
        closed=closed,
        none=none,
        unsynced=unsynced,
        pct=pct,
        median_time_to_merge_s=_median_int(ttm),
        median_review_comments=_median_int(rc),
    )


@dataclass(frozen=True)
class StruggleSummary:
    """v3.2 in-session struggle. Tool errors are universally captured;
    rejections are captured only by interaction-aware collectors
    (Cursor today), so they are gated and always reported with their
    coverage — never a misleading bare 0."""

    tool_error_total: int | None
    tool_error_rate: float | None
    rejection_total: int | None
    rejection_rate: float | None
    rejection_covered: int  # sessions with interaction_data_available
    rejection_total_sessions: int  # all sessions in the window
    rejection_overlaps_errors: bool = False  # v3.3: rejections are a subset of tool_errors


def struggle_signals(sessions: list[AiSession]) -> StruggleSummary:
    """Reduce already-parsed sessions to struggle stats. No window of
    its own — the caller passes the slice it wants (the panels pass the
    same 30-day `recent` they use for `summarize`). Fail-closed: any
    figure that cannot be derived from present data is None, never 0."""
    tool_calls = sum(s.tool_calls for s in sessions if s.tool_calls is not None)
    has_tool_data = any(s.tool_calls is not None for s in sessions)
    tool_errs = sum(s.tool_errors for s in sessions if s.tool_errors is not None)
    tool_error_total = tool_errs if has_tool_data else None
    tool_error_rate = (tool_errs / tool_calls) if tool_calls else None

    captured = [s for s in sessions if s.interaction_data_available is True]
    rej = sum(s.rejected_suggestion_count or 0 for s in captured)
    acc = sum(s.accepted_suggestion_count or 0 for s in captured)
    if captured:
        rejection_total: int | None = rej
        rejection_rate = (rej / (rej + acc)) if (rej + acc) else None
        # v3.3: for Claude Code and Codex, rejections are counted inside tool_errors.
        # Cursor rejections are distinct from tool_errors.
        overlaps = any(s.tool in {"claude-code", "codex"} for s in captured)
    else:
        rejection_total = None
        rejection_rate = None
        overlaps = False

    return StruggleSummary(
        tool_error_total=tool_error_total,
        tool_error_rate=tool_error_rate,
        rejection_total=rejection_total,
        rejection_rate=rejection_rate,
        rejection_covered=len(captured),
        rejection_total_sessions=len(sessions),
        rejection_overlaps_errors=overlaps,
    )


def summarize_struggle(sessions: list[AiSession], now: datetime) -> StruggleSummary:
    """30-day-windowed struggle rollup (same window as `summarize`)."""
    cutoff = now - timedelta(days=LEVERAGE_WINDOW_DAYS)
    return struggle_signals([s for s in sessions if s.start >= cutoff])


@dataclass(frozen=True)
class McpRollup:
    """v3.4 capability rollup over the window. Reported from the single
    most-MCP-heavy session (a coherent data point, not a cross-session
    statistic): its distinct-server count + its allowlisted names. The
    count may exceed the names — non-allowlisted servers are counted,
    never named."""

    peak_servers: int
    named: tuple[str, ...]  # allowlisted only, sorted


def summarize_mcp(sessions: list[AiSession], now: datetime) -> McpRollup | None:
    """None when no session in the 30-day window has MCP usage (so the
    surface omits the line — never an implied "0 servers")."""
    cutoff = now - timedelta(days=LEVERAGE_WINDOW_DAYS)
    recent = [s for s in sessions if s.start >= cutoff and s.mcp_servers_used is not None]
    if not recent:
        return None
    peak = max(recent, key=lambda s: s.mcp_servers_used or 0)
    # v5.16/B19: enforce the documented "allowlisted only, sorted" invariant
    # of McpRollup.named here, not only at write time. The stored CSV
    # ``mcp_server_names`` is attacker-influenceable (a hand-edited log), and
    # a non-allowlisted value like ``x[/notopened]`` would otherwise reach
    # render_mcp_phrase and crash the TUI via rich.markup (MarkupError).
    # Allowlisted names are safe identifiers, so filtering closes the vector
    # at the source for both the web and TUI surfaces.
    names = tuple(
        sorted(
            n for n in (peak.mcp_server_names or "").split(",") if n and n in MCP_SERVER_ALLOWLIST
        )
    )
    return McpRollup(peak_servers=peak.mcp_servers_used or 0, named=names)


def render_mcp_phrase(m: McpRollup) -> str:
    """Single source for the capability line so web and TUI cannot
    diverge. Names are allowlisted-only; '+N' covers counted-but-unnamed
    (non-allowlisted) servers."""
    plural = "s" if m.peak_servers != 1 else ""
    if not m.named:
        return f"MCP: {m.peak_servers} server{plural} (none on allowlist)"
    extra = m.peak_servers - len(m.named)
    tail = f" +{extra}" if extra > 0 else ""
    return f"MCP: {m.peak_servers} server{plural} ({', '.join(m.named)}{tail})"


def render_rejection_phrase(s: StruggleSummary) -> str:
    """The R3 honesty rule in one place: rejections are never a bare 0.

    Either the count with explicit coverage, or "not captured"."""
    if s.rejection_covered == 0 or s.rejection_total is None:
        return "rejections: not captured"
    pct = "" if s.rejection_rate is None else f" ({s.rejection_rate:.0%})"
    overlap = " (overlaps tool_errors)" if s.rejection_overlaps_errors else ""
    return (
        f"rejections {s.rejection_total}{pct}{overlap} "
        f"(over {s.rejection_covered} of {s.rejection_total_sessions} sessions; "
        f"rest: not captured)"
    )
