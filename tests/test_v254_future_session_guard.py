"""v2.54 — future-dated sessions are impossible: read-guard + seed-demo fix."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session, parse_sessions
from halyard.cli import app
from halyard.collectors import session_is_implausible, session_starts_in_future

_NOW = datetime(2026, 5, 16, 8, 38, 0)


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n")
    (p / AI_LOG_FILENAME).write_text(HEADER)
    return p


def _s(start: datetime, *, project: str | None = "kormilo:halyard") -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=10),
        tool="claude-code",
        model="claude-opus-4-7",
        input_tokens=100,
        output_tokens=50,
        cost_usd=1.0,
        project=project,
    )


def test_future_start_detected() -> None:
    future = _s(_NOW + timedelta(days=2), project=None)
    assert session_starts_in_future(future, now=_NOW) is True
    assert session_is_implausible(future, now=_NOW) is True


def test_recent_past_is_fine() -> None:
    recent = _s(_NOW - timedelta(minutes=30))
    assert session_starts_in_future(recent, now=_NOW) is False
    assert session_is_implausible(recent, now=_NOW) is False


def test_small_clock_skew_tolerated() -> None:
    # A couple minutes ahead (benign skew) is not "future".
    skewed = _s(_NOW + timedelta(minutes=2))
    assert session_starts_in_future(skewed, now=_NOW) is False


def test_parse_sessions_excludes_future_keeps_file(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    real = _s(datetime(2026, 5, 15, 23, 57))
    future = _s(datetime(2026, 5, 20, 17, 23), project=None)  # days ahead
    append_session(proj, real)
    append_session(proj, future)

    before = (proj / AI_LOG_FILENAME).read_text()
    got = parse_sessions(proj)

    assert len(got) == 1
    assert got[0].start == datetime(2026, 5, 15, 23, 57)
    # Raw line preserved on disk (read-only exclusion, like v2.53).
    assert (proj / AI_LOG_FILENAME).read_text() == before
    assert sum(1 for ln in before.splitlines() if ln.startswith("s ")) == 2


def test_seed_demo_never_writes_future_sessions(tmp_path: Path) -> None:
    _proj(tmp_path)
    with patch("halyard.ai_log.find_project_dir", return_value=tmp_path):
        result = CliRunner().invoke(app, ["seed-demo", "--yes"])
    assert result.exit_code == 0

    # Read raw lines (parse_sessions would hide any future ones, so
    # assert the writer itself produced none).
    now = datetime.now()
    starts = [
        AiSession.from_log_line(ln).start  # type: ignore[union-attr]
        for ln in (tmp_path / AI_LOG_FILENAME).read_text().splitlines()
        if ln.startswith("s ")
    ]
    assert starts, "seed-demo wrote nothing"
    assert max(starts) < now, f"seed-demo wrote a future session: {max(starts)}"
    # And every seeded session survives parse_sessions (none filtered).
    assert len(parse_sessions(tmp_path)) == len(starts)


def test_tz_aware_log_row_does_not_crash_parse(tmp_path: Path) -> None:
    """Regression: a tz-aware ISO timestamp must not crash parse_sessions.

    datetime.fromisoformat() yields an aware datetime for '...+00:00';
    the future guard compares against naive datetime.now(). Mixing the
    two raises TypeError and would take down every read path. Parsed
    timestamps must be normalised to naive local.
    """
    _proj(tmp_path / "p")
    log = tmp_path / "p" / AI_LOG_FILENAME
    with log.open("a") as fh:
        fh.write(
            "s 2026-05-15T10:00:00+00:00 2026-05-15T10:05:00+00:00 "
            "claude-code claude-opus-4-7 100 50 1.0 project=kormilo:halyard\n"
        )

    got = parse_sessions(tmp_path / "p")  # must not raise
    assert len(got) == 1
    assert got[0].start.tzinfo is None
    assert got[0].end.tzinfo is None
    assert session_starts_in_future(got[0]) is False
    assert session_is_implausible(got[0]) is False


def test_session_starts_in_future_handles_aware_input() -> None:

    s = AiSession(
        start=datetime(2026, 5, 15, 10, tzinfo=UTC),
        end=datetime(2026, 5, 15, 10, 5, tzinfo=UTC),
        tool="claude-code",
        model="claude-opus-4-7",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
        project="p",
    )
    # Naive 'now' vs aware start must not raise.
    assert session_starts_in_future(s, now=datetime(2026, 5, 16, 9)) is False
