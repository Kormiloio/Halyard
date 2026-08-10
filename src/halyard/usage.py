"""Usage analytics aggregation for dashboard and TUI surfaces."""

from __future__ import annotations

import math
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
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    api_only: bool = True,
    accounts: set[str] | None = None,
    places: int = 4,
) -> float:
    """Single spend-summing convention shared by budget and invoicing.

    Window is half-open on session *end* (period_start <= end < period_end)
    so a session is billed in the period it completed. If periods are None,
    all sessions are summed. Result is quantized with ROUND_HALF_UP so
    totals are deterministic across views.
    """
    total = Decimal(0)
    for s in sessions:
        if api_only and (s.billing != "api" or s.cost_usd <= 0):
            continue
        if accounts is not None and s.project not in accounts:
            continue
        if period_start is not None and s.end < period_start:
            continue
        if period_end is not None and s.end >= period_end:
            continue
        # v5.16/B1 backstop: a non-finite cost reaching here (e.g. via the
        # SQLite cache or direct AiSession construction, bypassing the
        # parse-time guard) would raise decimal.InvalidOperation (inf) or
        # poison the total to NaN. Skip it; the parse-side reject is primary.
        if not math.isfinite(s.cost_usd):
            continue
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
    total_messages: int
    message_data_missing_sessions: int
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
    # False when the tool reports no tokens or cost at all (Antigravity),
    # so surfaces can render "n/a" instead of "$0.00". A zero reads as
    # "this work was free"; n/a reads as "this was never measured".
    spend_tracked: bool = True


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
    # Per-day per-model fresh input/output split (v2.64). Real data — not
    # the window-wide proportional approximation the old chart used.
    model_io: dict[str, tuple[int, int]]

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
        total_messages=sum(_known_messages(s) for s in selected),
        message_data_missing_sessions=sum(1 for s in selected if not _has_message_data(s)),
        # v5.17/B17: headline must equal the sum of the breakdown bars, which
        # all use sum_spend(api_only=True) (Decimal-quantized). The old raw
        # sum(s.cost_usd) folded in credits/subscription cost the bars exclude,
        # so "captured" never matched the chart. Use the same convention here.
        total_cost_usd=sum_spend(selected),
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


def _has_message_data(session: AiSession) -> bool:
    """True if the session carries any user/assistant message count.

    Mirrors the token-missing pattern: an absent count is *missing*, not
    a fabricated 0, so it is excluded from the total and counted in
    `message_data_missing_sessions` instead.
    """
    return session.user_message_count is not None or session.assistant_message_count is not None


def _known_messages(session: AiSession) -> int:
    if not _has_message_data(session):
        return 0
    return (session.user_message_count or 0) + (session.assistant_message_count or 0)


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
    from halyard.model_breakdown import iter_model_usage
    from halyard.model_breakdown import parse as _parse_breakdown

    sessions = by_day.get(day, [])
    model_tokens: dict[str, int] = defaultdict(int)
    model_io: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for session in sessions:
        model_tokens[session.model] += _tokens(session)
        # Per-model in/out split — multi-model aware (mirrors _model_buckets)
        # so a router/main/subagent session attributes to each real model.
        if _parse_breakdown(session.model_breakdown) is not None:
            for model, m_in, m_out, _cr, _cw, _cost in iter_model_usage(session):
                io = model_io[model]
                io[0] += m_in
                io[1] += m_out
        else:
            io = model_io[session.model]
            io[0] += _known_input(session)
            io[1] += _known_output(session)
    return DailyUsageBucket(
        day=day,
        sessions=len(sessions),
        input_tokens=sum(_known_input(s) for s in sessions),
        output_tokens=sum(_known_output(s) for s in sessions),
        cache_read_tokens=sum(s.cache_read or 0 for s in sessions if s.tokens_available),
        cache_write_tokens=sum(s.cache_write or 0 for s in sessions if s.tokens_available),
        cost_usd=sum_spend(sessions),
        has_missing_token_data=any(not s.tokens_available for s in sessions),
        model_tokens=dict(model_tokens),
        model_io={m: (io[0], io[1]) for m, io in model_io.items()},
    )


def _model_buckets(sessions: list[AiSession]) -> list[ModelUsageBucket]:
    from halyard.model_breakdown import iter_model_usage
    from halyard.model_breakdown import parse as _parse_breakdown

    # model -> {field: sum}
    rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "sessions": 0,
            "input": 0,
            "output": 0,
            "cache_read": 0,
            "cache_write": 0,
        }
    )
    # model -> list[AiSession] (for sum_spend)
    model_sessions: dict[str, list[AiSession]] = defaultdict(list)
    # model -> sum of cost segments (for multi-model sessions)
    multi_model_costs: dict[str, Decimal] = defaultdict(Decimal)

    for session in sessions:
        if _parse_breakdown(session.model_breakdown) is not None:
            # Multi-model: attribute each model its own tokens + cost.
            # v5.17/B17: cost must obey the SAME billing filter the single-model
            # branch applies via sum_spend(api_only=True) — otherwise an
            # identical subscription session shows cost here but $0 there.
            # Tokens are real regardless of billing, so only the cost is gated.
            cost_billable = session.billing == "api" and session.cost_usd > 0
            for model, m_in, m_out, m_cr, m_cw, m_cost in iter_model_usage(session):
                row = rows[model]
                row["sessions"] += 1
                row["input"] += m_in
                row["output"] += m_out
                row["cache_read"] += m_cr
                row["cache_write"] += m_cw
                if cost_billable:
                    multi_model_costs[model] += Decimal(str(m_cost))
            continue

        # Single-model: byte-identical to pre-v2.61 behaviour.
        row = rows[session.model]
        row["sessions"] += 1
        row["input"] += _known_input(session)
        row["output"] += _known_output(session)
        row["cache_read"] += (session.cache_read or 0) if session.tokens_available else 0
        row["cache_write"] += (session.cache_write or 0) if session.tokens_available else 0
        model_sessions[session.model].append(session)

    # Calculate final costs per model
    final_costs: dict[str, float] = {}
    for model in rows:
        cost = multi_model_costs[model]
        if model in model_sessions:
            cost += Decimal(str(sum_spend(model_sessions[model])))
        final_costs[model] = float(cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    total_tokens = sum(
        row["input"] + row["output"] + row["cache_read"] + row["cache_write"]
        for row in rows.values()
    )
    total_cost = sum(final_costs.values())
    total_sessions = sum(row["sessions"] for row in rows.values())
    buckets = [
        ModelUsageBucket(
            model=model,
            sessions=row["sessions"],
            input_tokens=row["input"],
            output_tokens=row["output"],
            cache_read_tokens=row["cache_read"],
            cache_write_tokens=row["cache_write"],
            cost_usd=final_costs[model],
            token_share=_share(
                row["input"] + row["output"] + row["cache_read"] + row["cache_write"],
                total_tokens,
            ),
            cost_share=_share(final_costs[model], total_cost),
            session_share=_share(row["sessions"], total_sessions),
        )
        for model, row in rows.items()
    ]
    return sorted(buckets, key=lambda b: (-b.tokens, -b.cost_usd, b.model))


def _tool_buckets(sessions: list[AiSession]) -> list[ToolUsageBucket]:
    # tool -> {field: sum}
    rows: dict[str, dict[str, int]] = defaultdict(lambda: {"sessions": 0, "tokens": 0})
    # tool -> list[AiSession] (for sum_spend)
    tool_sessions: dict[str, list[AiSession]] = defaultdict(list)

    for session in sessions:
        row = rows[session.tool]
        row["sessions"] += 1
        row["tokens"] += _tokens(session)
        tool_sessions[session.tool].append(session)

    total_sessions = sum(row["sessions"] for row in rows.values())
    buckets = [
        ToolUsageBucket(
            tool=tool,
            sessions=row["sessions"],
            tokens=row["tokens"],
            cost_usd=sum_spend(tool_sessions[tool]),
            session_share=_share(row["sessions"], total_sessions),
        )
        for tool, row in rows.items()
    ]
    return sorted(buckets, key=lambda b: (-b.sessions, b.tool))


def _share(value: int | float, total: int | float) -> float:
    if total <= 0:
        return 0.0
    return float(value) / float(total)
