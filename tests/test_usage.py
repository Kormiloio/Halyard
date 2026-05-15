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


# ---------------------------------------------------------------------------
# v2.23 §6: empty data, tie-breaking, fallback, share calculations, CLI JSON
# ---------------------------------------------------------------------------


def test_empty_session_data_yields_zero_summary() -> None:
    """No sessions → all-zero summary, no streak, no peak hour, no favorite."""
    analytics = build_usage_analytics([], now=datetime(2026, 5, 14, 12))
    s = analytics.summary
    assert s.sessions == 0
    assert s.total_tokens == 0
    assert s.total_cost_usd == 0.0
    assert s.active_days == 0
    assert s.current_streak_days == 0
    assert s.longest_streak_days == 0
    assert s.peak_hour is None
    assert s.favorite_model is None
    assert analytics.daily == [] or all(d.sessions == 0 for d in analytics.daily)
    assert analytics.by_model == []
    assert analytics.by_tool == []


def test_peak_hour_tie_breaking_picks_earliest_hour() -> None:
    """When two hours tie for most session starts, the earlier hour wins."""
    now = datetime(2026, 5, 14, 12)
    sessions = [
        # Two sessions starting at 10:xx, two at 14:xx → tie.
        _session(start=datetime(2026, 5, 14, 10, 5)),
        _session(start=datetime(2026, 5, 14, 10, 30)),
        _session(start=datetime(2026, 5, 14, 14, 5)),
        _session(start=datetime(2026, 5, 14, 14, 30)),
    ]
    s = build_usage_analytics(sessions, now=now).summary
    # Earlier hour wins the tie.
    assert s.peak_hour == 10


def test_favorite_model_fallback_to_session_count_when_zero_tokens() -> None:
    """When every model has zero tokens, favorite_model falls back to session count.

    The token-volume-based pick can't rank when every model has zero
    tokens, so the fallback ranks by session count instead, with model
    name as a final tie-breaker.
    """
    now = datetime(2026, 5, 14, 12)
    sessions = [
        # model-a: 2 sessions, zero tokens. model-b: 1 session, zero tokens.
        _session(start=datetime(2026, 5, 14, 9), model="model-a", input_tokens=0, output_tokens=0),
        _session(start=datetime(2026, 5, 14, 10), model="model-a", input_tokens=0, output_tokens=0),
        _session(start=datetime(2026, 5, 14, 11), model="model-b", input_tokens=0, output_tokens=0),
    ]
    s = build_usage_analytics(sessions, now=now).summary
    assert s.favorite_model == "model-a"


def test_model_and_tool_share_calculations() -> None:
    """Model token_share and tool session_share are proportional to inputs."""
    now = datetime(2026, 5, 14, 12)
    sessions = [
        _session(start=datetime(2026, 5, 14, 9), model="m-a", tool="t-a", input_tokens=300),
        _session(start=datetime(2026, 5, 14, 10), model="m-a", tool="t-a", input_tokens=300),
        _session(start=datetime(2026, 5, 14, 11), model="m-b", tool="t-b", input_tokens=400),
    ]
    a = build_usage_analytics(sessions, now=now)

    by_model = {b.model: b for b in a.by_model}
    # m-a: 600 input + 100 output = 700 tokens. m-b: 400 + 50 = 450. Total 1150.
    assert by_model["m-a"].token_share > by_model["m-b"].token_share
    assert sum(b.token_share for b in a.by_model) > 0.99  # ~1.0

    by_tool = {b.tool: b for b in a.by_tool}
    assert by_tool["t-a"].sessions == 2
    assert by_tool["t-b"].sessions == 1


def test_cli_usage_json_output(
    tmp_path: Path,  # noqa: F821
    monkeypatch,  # type: ignore[no-untyped-def]
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    """halyard usage --json emits a parseable JSON payload with summary keys."""
    import json
    from pathlib import Path as _Path

    from typer.testing import CliRunner

    from halyard.ai_log import AI_LOG_FILENAME
    from halyard.cli import app

    # Set up a minimal hub project so the command resolves to a real dir.
    hub = tmp_path / "hub"
    hub.mkdir()
    (hub / "halyard.toml").write_text("[project]\nslug = 'test'\n")
    (hub / AI_LOG_FILENAME).write_text(
        "; halyard log\n"
        "s 2026-05-14T10:00:00 2026-05-14T10:30:00 claude-code sonnet 1000 200 0.0030 "
        "project=acme:web\n"
    )

    # Point hub-pointer and HOME at tmp_path.
    monkeypatch.setattr(_Path, "home", lambda: tmp_path)
    (tmp_path / ".halyard").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".halyard" / "hub").write_text(str(hub) + "\n")

    runner = CliRunner()
    result = runner.invoke(app, ["usage", "--json", "--range", "all"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "summary" in payload
    assert "by_model" in payload
    assert "by_tool" in payload
    assert payload["summary"]["sessions"] == 1
