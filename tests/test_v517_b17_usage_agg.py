"""v5.17/B17 regression — headline cost must equal the sum of the bars.

Two defects, one root cause (inconsistent billing convention):

  * ``UsageSummary.total_cost_usd`` summed ``s.cost_usd`` raw over ALL
    sessions (unquantized, includes credits/subscription), while every
    breakdown bar uses ``sum_spend(api_only=True)``. The headline thus
    folded in non-captured cost and never equalled the bars.

  * ``_model_buckets`` attributed multi-model cost via
    ``iter_model_usage``/``calculate_cost`` (ignores billing) but
    single-model cost via ``sum_spend(api_only=True)`` (drops
    ``billing != "api"``), so two identical subscription sessions showed
    cost in one path and ``$0`` in the other.

The fix picks ONE convention — ``sum_spend(api_only=True)`` — and applies
it uniformly. These tests pin both the malicious/buggy mixed-billing case
and the benign all-API case (guard against over-restriction).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from halyard.ai_log import AiSession
from halyard.model_breakdown import ModelSeg, encode
from halyard.usage import build_usage_analytics, sum_spend

_NOW = datetime(2026, 5, 14, 12)


def _session(
    *,
    start: datetime,
    model: str = "claude-sonnet-4-6",
    cost_usd: float,
    billing: str = "api",
    credits: float | None = None,
    model_breakdown: str | None = None,
    input_tokens: int = 1000,
    output_tokens: int = 500,
) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=10),
        tool="claude-code",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        project="acme:auth",
        billing=billing,
        credits=credits,
        model_breakdown=model_breakdown,
    )


# ---------------------------------------------------------------------------
# Defect 1 — headline == sum of bars, under mixed billing (buggy input)
# ---------------------------------------------------------------------------


def test_headline_excludes_subscription_cost_and_equals_bars() -> None:
    """A subscription session with a phantom cost_usd must not inflate the
    headline; the headline must equal the sum of the per-model bars."""
    sessions = [
        _session(start=datetime(2026, 5, 14, 9), cost_usd=0.02, billing="api"),
        # Subscription/credits session that nonetheless carries a cost_usd
        # value (the "phantom subscription cost" of B17). api_only excludes it.
        _session(
            start=datetime(2026, 5, 14, 10),
            cost_usd=5.00,
            billing="credits",
            credits=20.0,
        ),
    ]

    analytics = build_usage_analytics(sessions, now=_NOW)

    # Old buggy headline would have been 0.02 + 5.00 = 5.02 (raw sum).
    assert analytics.summary.total_cost_usd == sum_spend(sessions)
    assert analytics.summary.total_cost_usd == 0.02

    # Headline equals the sum of the rendered bars exactly.
    bars_total = round(sum(b.cost_usd for b in analytics.by_model), 2)
    assert round(analytics.summary.total_cost_usd, 2) == bars_total
    tool_total = round(sum(b.cost_usd for b in analytics.by_tool), 2)
    assert round(analytics.summary.total_cost_usd, 2) == tool_total


# ---------------------------------------------------------------------------
# Defect 2 — multi-model vs single-model billing parity (buggy input)
# ---------------------------------------------------------------------------


def test_multi_model_subscription_session_costs_zero_like_single_model() -> None:
    """Two identical subscription sessions — one single-model, one with a
    multi-model breakdown — must both contribute $0 cost. Pre-fix, the
    multi-model path attributed real calculate_cost() while the single-model
    path dropped it via api_only, so the bars disagreed."""
    breakdown = encode(
        [
            ModelSeg("claude-sonnet-4-6", 1000, 500, 0, 0),
            ModelSeg("gpt-4o", 200, 100, 0, 0),
        ]
    )
    single = _session(
        start=datetime(2026, 5, 14, 9),
        cost_usd=5.00,
        billing="credits",
        credits=20.0,
    )
    multi = _session(
        start=datetime(2026, 5, 14, 10),
        cost_usd=5.00,
        billing="credits",
        credits=20.0,
        model_breakdown=breakdown,
    )

    analytics = build_usage_analytics([single, multi], now=_NOW)

    # Every model bar must show $0 cost — neither billing path leaks cost.
    for bucket in analytics.by_model:
        assert bucket.cost_usd == 0.0, bucket
    assert analytics.summary.total_cost_usd == 0.0

    # Tokens are real regardless of billing — multi-model attribution stays.
    by_model = {b.model: b for b in analytics.by_model}
    assert "gpt-4o" in by_model  # multi-model segment still tokenized
    assert by_model["gpt-4o"].tokens == 300


# ---------------------------------------------------------------------------
# Benign input — all-API sessions still report full captured cost
# ---------------------------------------------------------------------------


def test_all_api_sessions_still_show_full_cost() -> None:
    """Guard against over-restriction: ordinary API-billed sessions (single
    and multi-model) must still report their full cost and reconcile."""
    breakdown = encode(
        [
            ModelSeg("claude-sonnet-4-6", 100000, 50000, 0, 0),
            ModelSeg("gpt-4o", 100000, 50000, 0, 0),
        ]
    )
    single = _session(start=datetime(2026, 5, 14, 9), cost_usd=0.50, billing="api")
    multi = _session(
        start=datetime(2026, 5, 14, 10),
        cost_usd=1.80,
        billing="api",
        model_breakdown=breakdown,
        input_tokens=200000,
        output_tokens=100000,
    )

    analytics = build_usage_analytics([single, multi], now=_NOW)

    # sonnet 1.05 + gpt-4o 0.75 = 1.80 for the multi-model session; the
    # single-model session contributes its own 0.50 via sum_spend.
    assert analytics.summary.total_cost_usd == sum_spend([single, multi])
    assert round(analytics.summary.total_cost_usd, 2) == 2.30

    bars_total = round(sum(b.cost_usd for b in analytics.by_model), 2)
    assert round(analytics.summary.total_cost_usd, 2) == bars_total

    by_model = {b.model: b for b in analytics.by_model}
    # Multi-model segments carry their independently-costed share.
    assert round(by_model["claude-sonnet-4-6"].cost_usd, 2) == 1.05 + 0.50
    assert round(by_model["gpt-4o"].cost_usd, 2) == 0.75


def test_zero_cost_api_session_contributes_nothing() -> None:
    """A genuinely free ($0) API session is excluded by api_only's
    cost_usd <= 0 guard in both headline and bars — no negative surprise."""
    sessions = [
        _session(start=datetime(2026, 5, 14, 9), cost_usd=0.0, billing="api"),
    ]
    analytics = build_usage_analytics(sessions, now=_NOW)
    assert analytics.summary.total_cost_usd == 0.0
    assert all(b.cost_usd == 0.0 for b in analytics.by_model)
