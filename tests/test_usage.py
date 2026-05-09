"""Tests for shared usage analytics."""

from __future__ import annotations

from datetime import datetime, timedelta

from halyard.ai_log import AiSession
from halyard.usage import build_usage_analytics


def _session(
    *,
    start: datetime,
    model: str = "claude-sonnet-4-6",
    tool: str = "claude-code",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cost_usd: float = 0.01,
    project: str | None = "acme:auth",
    tokens_available: bool = True,
) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=10),
        tool=tool,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        project=project,
        tokens_available=tokens_available,
    )


def test_usage_summary_metrics() -> None:
    now = datetime(2026, 5, 9, 12)
    sessions = [
        _session(start=datetime(2026, 5, 9, 9), input_tokens=1000, output_tokens=500),
        _session(
            start=datetime(2026, 5, 8, 10),
            model="gemini-2.0-flash",
            tool="gemini-cli",
            input_tokens=200,
            output_tokens=100,
            project=None,
        ),
    ]

    usage = build_usage_analytics(sessions, range_key="30d", now=now)

    assert usage.summary.sessions == 2
    assert usage.summary.total_tokens == 1800
    assert usage.summary.active_days == 2
    assert usage.summary.current_streak_days == 2
    assert usage.summary.longest_streak_days == 2
    assert usage.summary.peak_hour == 9
    assert usage.summary.favorite_model == "claude-sonnet-4-6"
    assert usage.summary.unattributed_sessions == 1


def test_usage_range_excludes_old_sessions() -> None:
    now = datetime(2026, 5, 9, 12)
    sessions = [
        _session(start=datetime(2026, 5, 9, 9)),
        _session(start=datetime(2026, 4, 1, 9)),
    ]

    usage = build_usage_analytics(sessions, range_key="7d", now=now)

    assert usage.summary.sessions == 1
    assert len(usage.daily) == 7


def test_missing_token_data_not_counted_as_zero_usage() -> None:
    now = datetime(2026, 5, 9, 12)
    sessions = [
        _session(
            start=datetime(2026, 5, 9, 9),
            input_tokens=999,
            output_tokens=999,
            tokens_available=False,
        )
    ]

    usage = build_usage_analytics(sessions, range_key="7d", now=now)

    assert usage.summary.sessions == 1
    assert usage.summary.total_tokens == 0
    assert usage.summary.token_data_missing_sessions == 1
    assert usage.daily[-1].has_missing_token_data is True
