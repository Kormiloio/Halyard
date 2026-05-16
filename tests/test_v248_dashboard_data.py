"""v2.48 — dashboard data correctness regressions."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard import registry
from halyard.ai_log import AI_LOG_FILENAME, HEADER, AiSession, append_session


def _proj(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[business]\n")
    (p / "time.timeclock").write_text("; t\n")
    (p / AI_LOG_FILENAME).write_text(HEADER)
    return p


def _sess(start: datetime, tool: str = "claude-code", model: str = "claude-opus-4-7") -> AiSession:
    return AiSession(
        start=start,
        end=start + timedelta(minutes=2),
        tool=tool,
        model=model,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        project="kormilo:halyard",
    )


# --- build_ai_report session injection ------------------------------------


def test_build_ai_report_uses_given_sessions_not_dir(tmp_path: Path) -> None:
    from halyard.reports import build_ai_report

    proj = _proj(tmp_path / "p")  # empty log on disk
    s = _sess(datetime(2026, 5, 15, 10))
    rep = build_ai_report(proj, all_time=True, sessions=[s])
    assert len(rep.sessions) == 1
    # dir log is empty; proves the list was used, not the directory
    rep_dir = build_ai_report(proj, all_time=True)
    assert len(rep_dir.sessions) == 0


# --- aggregate sources + dedup --------------------------------------------


def test_aggregate_dirs_unions_registry_and_hub_skips_logless(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import reports

    a = _proj(tmp_path / "a")
    b = _proj(tmp_path / "b")
    logless = tmp_path / "c"
    logless.mkdir()
    (logless / "halyard.toml").write_text("[business]\n")  # no ai-sessions.log
    monkeypatch.setattr("halyard.registry.read_registry", lambda: [a, logless])
    monkeypatch.setattr("halyard.hub.find_hub", lambda: b)

    dirs = reports.aggregate_session_dirs()
    assert a in dirs and b in dirs and logless not in dirs


def test_aggregate_state_dedups_cross_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from halyard import reports

    a = _proj(tmp_path / "a")
    b = _proj(tmp_path / "b")
    s = _sess(datetime(2026, 5, 15, 9))
    append_session(a, s)
    append_session(b, s)  # same session in two source logs
    monkeypatch.setattr("halyard.reports.aggregate_session_dirs", lambda: [a, b])
    state = reports.build_aggregate_dashboard_state()
    assert len(state.all_sessions) == 1
    assert state.aggregate_count == 2


# --- implausible-session guard --------------------------------------------


def test_session_is_implausible() -> None:
    from halyard.collectors import session_is_implausible

    base = datetime(2026, 5, 15, 10)
    ok = _sess(base)
    assert session_is_implausible(ok) is False
    long = AiSession(
        start=datetime(2026, 5, 7, 10),
        end=datetime(2026, 5, 15, 17),
        tool="cursor",
        model="claude-3.5-sonnet",
        input_tokens=2000,
        output_tokens=400,
        cost_usd=0.0,
    )
    assert session_is_implausible(long) is True
    neg = AiSession(
        start=datetime(2026, 5, 7, 10, 0, 0),
        end=datetime(2026, 5, 7, 8, 58, 57),  # end before start
        tool="cursor",
        model="claude-3.5-sonnet",
        input_tokens=2000,
        output_tokens=400,
        cost_usd=0.0,
    )
    assert session_is_implausible(neg) is True


def test_cursor_drops_implausible_synthetic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from io import StringIO

    from halyard.collectors.cursor import handle_stop_hook

    proj = _proj(tmp_path / "proj")
    state_file = tmp_path / "cursor-session"
    state_file.write_text("2026-05-07T10:00:00")  # frozen ancient start
    monkeypatch.setattr("halyard.collectors.cursor._CURSOR_SESSION_FILE", state_file)
    monkeypatch.setattr("halyard.collectors.cursor.read_active_project", lambda: None)
    payload = {
        "model": "claude-3.5-sonnet",
        "workspace_roots": [str(proj)],
        "usage": {"input_tokens": 2000, "output_tokens": 400},
    }
    monkeypatch.setattr("sys.stdin", StringIO(json.dumps(payload)))
    handle_stop_hook()
    from halyard.ai_log import parse_sessions

    assert parse_sessions(proj) == []  # >8-day span rejected despite tokens


# --- registry tempdir guard -----------------------------------------------


def test_register_project_refuses_tempdir(tmp_path: Path) -> None:
    # tmp_path is under the system temp dir -> must be ignored.
    registry.register_project(tmp_path)
    raw = registry.REGISTRY_PATH
    assert (not raw.exists()) or str(tmp_path.resolve()) not in raw.read_text()
