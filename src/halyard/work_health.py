"""AI Work Health — signal detectors and report model (v2.7)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from halyard.ai_log import AiSession

# ---------------------------------------------------------------------------
# Thresholds (not user-configurable in v2.7)
# ---------------------------------------------------------------------------

_THRESHOLD_MIN_CALLS = 5
_THRESHOLD_ERROR_RATE = 0.25
_THRESHOLD_ACTIVE_RATIO = 0.3
_THRESHOLD_COST_USD = 0.50
_THRESHOLD_LINES_PER_DOLLAR = 5.0
_THRESHOLD_REPEATS = 3


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthSignal:
    category: str
    label: str
    sessions: list[AiSession]
    detail: str
    available: bool


@dataclass(frozen=True)
class WorkHealthReport:
    period: str
    session_count: int
    signals: list[HealthSignal]


# ---------------------------------------------------------------------------
# Signal detectors
# ---------------------------------------------------------------------------


def detect_high_error_rate(sessions: list[AiSession]) -> HealthSignal:
    available = any(s.tool_calls is not None for s in sessions)
    flagged = [
        s
        for s in sessions
        if s.tool_calls is not None
        and s.tool_calls >= _THRESHOLD_MIN_CALLS
        and (s.tool_errors or 0) / s.tool_calls > _THRESHOLD_ERROR_RATE
    ]
    return HealthSignal(
        category="high_error_rate",
        label="High tool error rate",
        sessions=flagged,
        detail="tool_calls",
        available=available,
    )


def detect_wall_vs_active(sessions: list[AiSession]) -> HealthSignal:
    available = any(
        s.wall_seconds is not None and s.agent_active_seconds is not None for s in sessions
    )
    flagged = [
        s
        for s in sessions
        if s.wall_seconds is not None
        and s.agent_active_seconds is not None
        and s.wall_seconds > 0
        and s.agent_active_seconds / s.wall_seconds < _THRESHOLD_ACTIVE_RATIO
    ]
    return HealthSignal(
        category="wall_vs_active",
        label="Wall time ≫ active time",
        sessions=flagged,
        detail="agent_active_seconds",
        available=available,
    )


def detect_high_spend_low_delta(sessions: list[AiSession]) -> HealthSignal:
    available = any(s.code_added is not None for s in sessions)
    flagged = [
        s
        for s in sessions
        if s.code_added is not None
        and s.cost_usd >= _THRESHOLD_COST_USD
        and (s.code_added + (s.code_removed or 0)) / s.cost_usd < _THRESHOLD_LINES_PER_DOLLAR
    ]
    return HealthSignal(
        category="high_spend_low_delta",
        label="High spend, low code delta",
        sessions=flagged,
        detail="code_added",
        available=available,
    )


def _day_key(s: AiSession) -> tuple[str, str, str]:
    # v5.19/B-health-branch: prefer the first-class `branch` field. Reading
    # only the legacy `branch:` tag falsely flagged three sessions on three
    # distinct modern branches as the "same" key (all empty), so unrelated
    # work was reported as "repeated attempts". The legacy tag is the
    # fallback for ledger lines written before AiSession.branch existed.
    branch = s.branch or next(
        (t.removeprefix("branch:") for t in s.tags if t.startswith("branch:")),
        "",
    )
    return (s.project or "", branch, s.start.strftime("%Y-%m-%d"))


def detect_repeated_attempts(sessions: list[AiSession]) -> HealthSignal:
    counts = Counter(_day_key(s) for s in sessions)
    # Only flag keys where the project is non-empty
    flagged_keys = {k for k, n in counts.items() if n >= _THRESHOLD_REPEATS and k[0]}
    flagged = [s for s in sessions if _day_key(s) in flagged_keys]
    return HealthSignal(
        category="repeated_attempts",
        label="Repeated sessions — same project/branch",
        sessions=flagged,
        detail="",
        available=True,
    )


def detect_unattributed_high_cost(sessions: list[AiSession]) -> HealthSignal:
    unattributed = [s for s in sessions if not s.project and s.cost_usd > 0]
    if not unattributed:
        return HealthSignal(
            category="unattributed_high_cost",
            label="Unattributed high-cost sessions",
            sessions=[],
            detail="",
            available=bool(sessions),
        )

    costs = sorted(s.cost_usd for s in sessions if s.cost_usd > 0)
    if costs:
        p75 = costs[int(len(costs) * 0.75)]
        flagged = [s for s in unattributed if s.cost_usd >= p75]
    else:
        flagged = list(unattributed)

    return HealthSignal(
        category="unattributed_high_cost",
        label="Unattributed high-cost sessions",
        sessions=flagged,
        detail="",
        available=True,
    )


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_health_report(sessions: list[AiSession], period: str) -> WorkHealthReport:
    signals = [
        detect_high_error_rate(sessions),
        detect_wall_vs_active(sessions),
        detect_high_spend_low_delta(sessions),
        detect_repeated_attempts(sessions),
        detect_unattributed_high_cost(sessions),
    ]
    return WorkHealthReport(period=period, session_count=len(sessions), signals=signals)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

_RULE = "─" * 53


def render_text(report: WorkHealthReport) -> str:
    lines: list[str] = []
    lines.append(f"AI Work Health — {report.period}")
    lines.append(_RULE)
    lines.append("")
    lines.append("These are operational signals, not productivity scores.")
    lines.append("")

    for sig in report.signals:
        if not sig.available:
            lines.append(f"● {sig.label:<42} No data — requires {sig.detail}")
        elif not sig.sessions:
            lines.append(f"● {sig.label:<42} 0 sessions flagged")
        else:
            count = len(sig.sessions)
            noun = "session" if count == 1 else "sessions"
            lines.append(f"● {sig.label:<42} {count} {noun} flagged")
            for s in sig.sessions:
                lines.append(_format_session_row(sig.category, s))
        lines.append("")

    lines.append(_RULE)
    lines.append(f"{report.session_count} sessions analysed.")
    return "\n".join(lines)


def _format_session_row(category: str, s: AiSession) -> str:
    ts = s.start.strftime("%Y-%m-%d %H:%M")
    proj = s.project or "(none)"

    if category == "high_error_rate":
        calls = s.tool_calls or 0
        errors = s.tool_errors or 0
        rate = int(errors / calls * 100) if calls else 0
        return f"  {ts}  {s.tool}  {proj}  {calls}c {errors}e ({rate}%)  ${s.cost_usd:.2f}"

    if category == "wall_vs_active":
        wall = s.wall_seconds or 0
        active = s.agent_active_seconds or 0
        ratio = f"{active / wall * 100:.0f}%" if wall else "?"
        return f"  {ts}  {s.tool}  {proj}  wall {wall}s  active {active}s  ({ratio})"

    if category == "high_spend_low_delta":
        added = s.code_added or 0
        removed = s.code_removed or 0
        return f"  {ts}  {s.tool}  {proj}  ${s.cost_usd:.2f}  +{added}/-{removed}"

    if category == "repeated_attempts":
        key = _day_key(s)
        branch = f":{key[1]}" if key[1] else ""
        return f"  {ts}  {s.tool}  {proj}{branch}"

    # unattributed_high_cost
    return f"  {ts}  {s.tool}  ${s.cost_usd:.2f}"


def render_json(report: WorkHealthReport) -> dict:  # type: ignore[type-arg]
    return {
        "period": report.period,
        "session_count": report.session_count,
        "signals": [_signal_to_dict(sig) for sig in report.signals],
    }


def _signal_to_dict(sig: HealthSignal) -> dict:  # type: ignore[type-arg]
    return {
        "category": sig.category,
        "label": sig.label,
        "available": sig.available,
        "flagged_count": len(sig.sessions),
        "sessions": [_session_summary(sig.category, s) for s in sig.sessions],
    }


def _session_summary(category: str, s: AiSession) -> dict:  # type: ignore[type-arg]
    base: dict = {  # type: ignore[type-arg]
        "start": s.start.isoformat(),
        "tool": s.tool,
        "project": s.project,
        "cost_usd": s.cost_usd,
    }
    if category == "high_error_rate":
        base["tool_calls"] = s.tool_calls
        base["tool_errors"] = s.tool_errors
    elif category == "wall_vs_active":
        base["wall_seconds"] = s.wall_seconds
        base["agent_active_seconds"] = s.agent_active_seconds
    elif category == "high_spend_low_delta":
        base["code_added"] = s.code_added
        base["code_removed"] = s.code_removed
    return base
