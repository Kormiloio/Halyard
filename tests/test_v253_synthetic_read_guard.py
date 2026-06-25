"""v2.53 — parse-time synthetic-telemetry guard."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session, parse_sessions
from halyard.collectors import session_is_synthetic_telemetry

_BASE = datetime.now().replace(hour=21, minute=0, second=0, microsecond=0) - timedelta(days=1)


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (p / AI_LOG_FILENAME).write_text(HEADER, encoding="utf-8")
    return p


def _s(
    *,
    inp: int,
    out: int,
    model: str,
    cost: float,
    project: str | None,
    start: datetime = _BASE,
) -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=10),
        tool="cursor",
        model=model,
        input_tokens=inp,
        output_tokens=out,
        cost_usd=cost,
        project=project,
    )


def test_exact_cursor_fingerprint_is_synthetic() -> None:
    s = _s(inp=2000, out=400, model="claude-3.5-sonnet", cost=0.0, project=None)
    assert session_is_synthetic_telemetry(s) is True


def test_exact_gemini_fingerprint_is_synthetic() -> None:
    s = _s(inp=100, out=50, model="gemini-2.0-pro", cost=0.0, project=None)
    assert session_is_synthetic_telemetry(s) is True


def test_nonzero_cost_is_real() -> None:
    s = _s(inp=2000, out=400, model="claude-3.5-sonnet", cost=1.20, project=None)
    assert session_is_synthetic_telemetry(s) is False


def test_attributed_is_real() -> None:
    s = _s(inp=2000, out=400, model="claude-3.5-sonnet", cost=0.0, project="kormilo:halyard")
    assert session_is_synthetic_telemetry(s) is False


def test_current_model_is_real() -> None:
    s = _s(inp=2000, out=400, model="claude-opus-4-7", cost=0.0, project=None)
    assert session_is_synthetic_telemetry(s) is False


def test_genuine_session_is_real() -> None:
    s = _s(inp=8123, out=2044, model="claude-opus-4-7", cost=6.21, project="kormilo:halyard")
    assert session_is_synthetic_telemetry(s) is False


def test_parse_sessions_excludes_synthetic_but_keeps_file(tmp_path: Path) -> None:
    proj = _proj(tmp_path / "p")
    real1 = _s(
        inp=5000,
        out=1200,
        model="claude-opus-4-7",
        cost=3.5,
        project="kormilo:halyard",
        start=_BASE,
    )
    real2 = _s(
        inp=900,
        out=200,
        model="claude-opus-4-7",
        cost=0.4,
        project="kormilo:halyard",
        start=_BASE + timedelta(hours=1),
    )
    syn1 = _s(
        inp=2000,
        out=400,
        model="claude-3.5-sonnet",
        cost=0.0,
        project=None,
        start=_BASE + timedelta(minutes=20),
    )
    syn2 = _s(
        inp=100,
        out=50,
        model="gemini-2.0-pro",
        cost=0.0,
        project=None,
        start=_BASE + timedelta(minutes=40),
    )
    for s in (real1, syn1, real2, syn2):
        append_session(proj, s)

    log_path = proj / AI_LOG_FILENAME
    before = log_path.read_text(encoding="utf-8")

    got = parse_sessions(proj)
    assert len(got) == 2
    assert all(s.project == "kormilo:halyard" for s in got)

    # Raw lines untouched on disk; 4 's' records still present.
    after = log_path.read_text(encoding="utf-8")
    assert before == after
    assert sum(1 for ln in after.splitlines() if ln.startswith("s ")) == 4
    # Idempotent: re-parsing does not mutate the file either.
    parse_sessions(proj)
    assert log_path.read_text(encoding="utf-8") == after


def test_aggregate_layer_inherits_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import mcp_server

    proj = _proj(tmp_path / "agg")
    append_session(
        proj,
        _s(
            inp=2000,
            out=400,
            model="claude-3.5-sonnet",
            cost=0.0,
            project=None,
            start=_BASE,
        ),
    )
    append_session(
        proj,
        _s(
            inp=4000,
            out=900,
            model="claude-opus-4-7",
            cost=2.1,
            project="kormilo:halyard",
            start=_BASE + timedelta(hours=1),
        ),
    )
    monkeypatch.setattr(mcp_server, "aggregate_session_dirs", lambda: [proj])
    summary = mcp_server._work_summary("30d")
    assert summary["sessions"] == 1
    assert summary["adrift_sessions"] == 0
