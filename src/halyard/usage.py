"""Usage analytics aggregation for dashboard and TUI surfaces."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from halyard.ai_log import AiSession


def round_money(value: float, places: int = 2) -> float:
    """Round a monetary value with ROUND_HALF_UP (not banker's rounding)."""
    quant = Decimal(1).scaleb(-places)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def sum_spend(
    sessions: list[AiSession],
    *,
    period_start: datetime,
    period_end: datetime,
    api_only: bool = True,
    accounts: set[str] | None = None,
    places: int = 4,
) -> float:
    """Single spend-summing convention shared by budget and invoicing.

    Window is half-open on session *end* (period_start <= end < period_end)
    so a session is billed in the period it completed. Result is quantized
    with ROUND_HALF_UP so totals are deterministic across views.
    """
    total = Decimal(0)
    for s in sessions:
        if api_only and (s.billing != "api" or s.cost_usd <= 0):
            continue
        if accounts is not None and s.project not in accounts:
            continue
        if period_start <= s.end < period_end:
            total += Decimal(str(s.cost_usd))
    quant = Decimal(1).scaleb(-places)  # e.g. places=2 -> Decimal("0.01")
    return float(total.quantize(quant, rounding=ROUND_HALF_UP))


UsageRangeKey = Literal["all", "30d", "7d"]


@dataclass(frozen=True)
class UsageRange:
    key: UsageRangeKey
    label: str
    start: date | None
    end: date


@dataclass(frozen=True)
class UsageSummary:
    sessions: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int
    token_data_missing_sessions: int
    total_cost_usd: float
    active_days: int
    current_streak_days: int
    longest_streak_days: int
    peak_hour: int | None
    favorite_model: str | None
    unattributed_sessions: int

    @property
    def total_tokens(self) -> int:
        return (
            self.total_input_tokens
            + self.total_output_tokens
            + self.total_cache_read_tokens
            + self.total_cache_write_tokens
        )


@dataclass(frozen=True)
class ModelUsageBucket:
    model: str
    sessions: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    token_share: float
    cost_share: float
    session_share: float

    @property
    def tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass(frozen=True)
class ToolUsageBucket:
    tool: str
    sessions: int
    tokens: int
    cost_usd: float
    session_share: float


@dataclass(frozen=True)
class DailyUsageBucket:
    day: date
    sessions: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    has_missing_token_data: bool
    model_tokens: dict[str, int]

    @property
    def tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass(frozen=True)
class UsageAnalytics:
    range: UsageRange
    summary: UsageSummary
    daily: list[DailyUsageBucket]
    by_model: list[ModelUsageBucket]
    by_tool: list[ToolUsageBucket]


def build_usage_analytics(
    sessions: list[AiSession],
    *,
    range_key: UsageRangeKey = "30d",
    now: datetime | None = None,
) -> UsageAnalytics:
    """Aggregate usage analytics for a selected local-date range."""
    clock = now or datetime.now()
    usage_range = _usage_range(range_key, sessions, clock)
    selected = _filter_sessions(sessions, usage_range)
    days = {s.start.date() for s in selected}

    summary = UsageSummary(
        sessions=len(selected),
        total_input_tokens=sum(_known_input(s) for s in selected),
        total_output_tokens=sum(_known_output(s) for s in selected),
        total_cache_read_tokens=sum(s.cache_read or 0 for s in selected if s.tokens_available),
        total_cache_write_tokens=sum(s.cache_write or 0 for s in selected if s.tokens_available),
        token_data_missing_sessions=sum(1 for s in selected if not s.tokens_available),
        total_cost_usd=sum(s.cost_usd for s in selected),
        active_days=len(days),
        current_streak_days=_current_streak(days, usage_range.end),
        longest_streak_days=_longest_streak(days),
        peak_hour=_peak_hour(selected),
        favorite_model=_favorite_model(selected),
        unattributed_sessions=sum(1 for s in selected if not s.project),
    )

    return UsageAnalytics(
        range=usage_range,
        summary=summary,
        daily=_daily_buckets(selected, usage_range),
        by_model=_model_buckets(selected),
        by_tool=_tool_buckets(selected),
    )


def compact_number(value: int | float) -> str:
    """Render large counts compactly for dense UI."""
    number = float(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    if number >= 1_000_000:
        return f"{sign}{number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{sign}{number / 1_000:.1f}k"
    return f"{sign}{int(number)}"


def _usage_range(range_key: UsageRangeKey, sessions: list[AiSession], now: datetime) -> UsageRange:
    end = now.date()
    if range_key == "7d":
        return UsageRange(key=range_key, label="7d", start=end - timedelta(days=6), end=end)
    if range_key == "30d":
        return UsageRange(key=range_key, label="30d", start=end - timedelta(days=29), end=end)
    start = min(s.start.date() for s in sessions) if sessions else end
    return UsageRange(key="all", label="All", start=start, end=end)


def _filter_sessions(sessions: list[AiSession], usage_range: UsageRange) -> list[AiSession]:
    if usage_range.start is None:
        return list(sessions)
    return [
        session
        for session in sessions
        if usage_range.start <= session.start.date() <= usage_range.end
    ]


def _known_input(session: AiSession) -> int:
    return session.input_tokens if session.tokens_available else 0


def _known_output(session: AiSession) -> int:
    return session.output_tokens if session.tokens_available else 0


def _tokens(session: AiSession) -> int:
    if not session.tokens_available:
        return 0
    return (
        session.input_tokens
        + session.output_tokens
        + (session.cache_read or 0)
        + (session.cache_write or 0)
    )


def _current_streak(days: set[date], end: date) -> int:
    streak = 0
    cursor = end
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _longest_streak(days: set[date]) -> int:
    if not days:
        return 0
    longest = 0
    current = 0
    previous: date | None = None
    for day in sorted(days):
        if previous is not None and day == previous + timedelta(days=1):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = day
    return longest


def _peak_hour(sessions: list[AiSession]) -> int | None:
    counts = Counter(session.start.hour for session in sessions)
    if not counts:
        return None
    max_count = max(counts.values())
    return min(hour for hour, count in counts.items() if count == max_count)


def _favorite_model(sessions: list[AiSession]) -> str | None:
    if not sessions:
        return None
    tokens_by_model: dict[str, int] = defaultdict(int)
    sessions_by_model: Counter[str] = Counter()
    for session in sessions:
        tokens_by_model[session.model] += _tokens(session)
        sessions_by_model[session.model] += 1
    if any(tokens_by_model.values()):
        return min(
            tokens_by_model,
            key=lambda model: (-tokens_by_model[model], -sessions_by_model[model], model),
        )
    return min(sessions_by_model, key=lambda model: (-sessions_by_model[model], model))


def _daily_buckets(
    sessions: list[AiSession],
    usage_range: UsageRange,
) -> list[DailyUsageBucket]:
    by_day: dict[date, list[AiSession]] = defaultdict(list)
    for session in sessions:
        by_day[session.start.date()].append(session)

    start = usage_range.start or usage_range.end
    days = (usage_range.end - start).days + 1
    return [_daily_bucket(start + timedelta(days=offset), by_day) for offset in range(days)]


def _daily_bucket(day: date, by_day: dict[date, list[AiSession]]) -> DailyUsageBucket:
    sessions = by_day.get(day, [])
    model_tokens: dict[str, int] = defaultdict(int)
    for session in sessions:
        model_tokens[session.model] += _tokens(session)
    return DailyUsageBucket(
        day=day,
        sessions=len(sessions),
        input_tokens=sum(_known_input(s) for s in sessions),
        output_tokens=sum(_known_output(s) for s in sessions),
        cache_read_tokens=sum(s.cache_read or 0 for s in sessions if s.tokens_available),
        cache_write_tokens=sum(s.cache_write or 0 for s in sessions if s.tokens_available),
        cost_usd=sum(s.cost_usd for s in sessions),
        has_missing_token_data=any(not s.tokens_available for s in sessions),
        model_tokens=dict(model_tokens),
    )


def _model_buckets(sessions: list[AiSession]) -> list[ModelUsageBucket]:
    rows: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "sessions": 0,
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
            "cost": 0.0,
        }
    )
    from halyard.model_breakdown import iter_model_usage
    from halyard.model_breakdown import parse as _parse_breakdown

    for session in sessions:
        if _parse_breakdown(session.model_breakdown) is not None:
            # Multi-model: attribute each model its own tokens + cost.
            for model, m_in, m_out, m_cr, m_cw, m_cost in iter_model_usage(session):
                row = rows[model]
                row["sessions"] = int(row["sessions"]) + 1
                row["input"] = int(row["input"]) + m_in
                row["output"] = int(row["output"]) + m_out
                row["cache_read"] = int(row["cache_read"]) + m_cr
                row["cache_write"] = int(row["cache_write"]) + m_cw
                row["cost"] = float(row["cost"]) + m_cost
            continue
        # Single-model: byte-identical to pre-v2.61 behaviour.
        row = rows[session.model]
        row["sessions"] = int(row["sessions"]) + 1
        row["input"] = int(row["input"]) + _known_input(session)
        row["output"] = int(row["output"]) + _known_output(session)
        row["cache_read"] = int(row["cache_read"]) + (
            (session.cache_read or 0) if session.tokens_available else 0
        )
        row["cache_write"] = int(row["cache_write"]) + (
            (session.cache_write or 0) if session.tokens_available else 0
        )
        row["cost"] = float(row["cost"]) + session.cost_usd

    total_tokens = sum(
        int(row["input"]) + int(row["output"]) + int(row["cache_read"]) + int(row["cache_write"])
        for row in rows.values()
    )
    total_cost = sum(float(row["cost"]) for row in rows.values())
    total_sessions = sum(int(row["sessions"]) for row in rows.values())
    buckets = [
        ModelUsageBucket(
            model=model,
            sessions=int(row["sessions"]),
            input_tokens=int(row["input"]),
            output_tokens=int(row["output"]),
            cache_read_tokens=int(row["cache_read"]),
            cache_write_tokens=int(row["cache_write"]),
            cost_usd=float(row["cost"]),
            token_share=_share(
                int(row["input"])
                + int(row["output"])
                + int(row["cache_read"])
                + int(row["cache_write"]),
                total_tokens,
            ),
            cost_share=_share(float(row["cost"]), total_cost),
            session_share=_share(int(row["sessions"]), total_sessions),
        )
        for model, row in rows.items()
    ]
    return sorted(buckets, key=lambda b: (-b.tokens, -b.cost_usd, b.model))


def _tool_buckets(sessions: list[AiSession]) -> list[ToolUsageBucket]:
    rows: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"sessions": 0, "tokens": 0, "cost": 0.0}
    )
    for session in sessions:
        row = rows[session.tool]
        row["sessions"] = int(row["sessions"]) + 1
        row["tokens"] = int(row["tokens"]) + _tokens(session)
        row["cost"] = float(row["cost"]) + session.cost_usd
    total_sessions = sum(int(row["sessions"]) for row in rows.values())
    buckets = [
        ToolUsageBucket(
            tool=tool,
            sessions=int(row["sessions"]),
            tokens=int(row["tokens"]),
            cost_usd=float(row["cost"]),
            session_share=_share(int(row["sessions"]), total_sessions),
        )
        for tool, row in rows.items()
    ]
    return sorted(buckets, key=lambda b: (-b.sessions, b.tool))


def _share(value: int | float, total: int | float) -> float:
    if total <= 0:
        return 0.0
    return float(value) / float(total)
