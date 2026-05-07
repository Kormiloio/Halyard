"""Tests for attribution confirmation — infer_project_attribution and confirm flow."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.ai_log import HEADER, AiSession, append_session
from halyard.cli import app

runner = CliRunner()


def _session(
    *,
    start: datetime | None = None,
    project: str | None = None,
    tool: str = "claude-code",
    cost: float = 1.0,
    minutes: int = 10,
) -> AiSession:
    start_time = start or datetime(2026, 5, 7, 10, 0)
    return AiSession(
        start=start_time,
        end=start_time + timedelta(minutes=minutes),
        tool=tool,
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=cost,
        project=project,
    )


def _tc(start: datetime, end: datetime, account: str) -> tuple[datetime, datetime, str]:
    return (start, end, account)


# ---------------------------------------------------------------------------
# infer_project_attribution
# ---------------------------------------------------------------------------


def test_infer_single_overlap_returns_project() -> None:
    from halyard.ledger import infer_project_attribution

    sess = _session(start=datetime(2026, 5, 7, 10, 0), minutes=10)
    tc = [_tc(datetime(2026, 5, 7, 9, 0), datetime(2026, 5, 7, 11, 0), "acme:auth")]

    assert infer_project_attribution(sess, tc) == "acme:auth"


def test_infer_ambiguous_overlap_returns_none() -> None:
    from halyard.ledger import infer_project_attribution

    sess = _session(start=datetime(2026, 5, 7, 10, 0), minutes=10)
    tc = [
        _tc(datetime(2026, 5, 7, 9, 0), datetime(2026, 5, 7, 11, 0), "acme:auth"),
        _tc(datetime(2026, 5, 7, 9, 30), datetime(2026, 5, 7, 10, 30), "globex:reports"),
    ]

    assert infer_project_attribution(sess, tc) is None


def test_infer_no_overlap_returns_none() -> None:
    from halyard.ledger import infer_project_attribution

    sess = _session(start=datetime(2026, 5, 7, 10, 0), minutes=10)
    tc = [_tc(datetime(2026, 5, 7, 12, 0), datetime(2026, 5, 7, 13, 0), "acme:auth")]

    assert infer_project_attribution(sess, tc) is None


def test_infer_empty_timeclock_returns_none() -> None:
    from halyard.ledger import infer_project_attribution

    sess = _session(start=datetime(2026, 5, 7, 10, 0))
    assert infer_project_attribution(sess, []) is None


def test_infer_exact_boundary_counts_as_overlap() -> None:
    from halyard.ledger import infer_project_attribution

    sess = _session(start=datetime(2026, 5, 7, 10, 0), minutes=10)
    # timeclock ends exactly when session starts — inclusive boundary, counts as overlap
    tc_touching_start = [_tc(datetime(2026, 5, 7, 9, 0), datetime(2026, 5, 7, 10, 0), "acme:auth")]
    # timeclock starts exactly when session ends — inclusive boundary, counts as overlap
    tc_touching_end = [_tc(datetime(2026, 5, 7, 10, 10), datetime(2026, 5, 7, 11, 0), "acme:auth")]

    assert infer_project_attribution(sess, tc_touching_start) == "acme:auth"
    assert infer_project_attribution(sess, tc_touching_end) == "acme:auth"


# ---------------------------------------------------------------------------
# confirm_session_attributions
# ---------------------------------------------------------------------------


def test_confirm_writes_project_to_matching_line(tmp_path: Path) -> None:
    from halyard.ai_log import confirm_session_attributions

    log = tmp_path / "ai-sessions.log"
    log.write_text(HEADER)
    sess = _session(project=None)
    append_session(tmp_path, sess)

    raw_line = next(
        line.rstrip()
        for line in log.read_text().splitlines()
        if line.startswith("s ")
    )

    changed = confirm_session_attributions(tmp_path, [(raw_line, "acme:auth")])

    assert changed == 1
    content = log.read_text()
    assert "project=acme:auth" in content


def test_confirm_does_not_touch_other_lines(tmp_path: Path) -> None:
    from halyard.ai_log import confirm_session_attributions

    log = tmp_path / "ai-sessions.log"
    log.write_text(HEADER)
    append_session(tmp_path, _session(project="acme:existing"))
    append_session(tmp_path, _session(project=None))

    raw_lines = [ln.rstrip() for ln in log.read_text().splitlines() if ln.startswith("s ")]
    unattributed_line = next(ln for ln in raw_lines if "project=" not in ln)

    changed = confirm_session_attributions(tmp_path, [(unattributed_line, "acme:new")])

    assert changed == 1
    lines = [ln for ln in log.read_text().splitlines() if ln.startswith("s ")]
    attributed = [ln for ln in lines if "project=acme:existing" in ln]
    new = [ln for ln in lines if "project=acme:new" in ln]
    assert len(attributed) == 1
    assert len(new) == 1


def test_confirm_empty_confirmations_returns_zero(tmp_path: Path) -> None:
    from halyard.ai_log import confirm_session_attributions

    log = tmp_path / "ai-sessions.log"
    log.write_text(HEADER)
    append_session(tmp_path, _session(project=None))

    changed = confirm_session_attributions(tmp_path, [])
    assert changed == 0


def test_confirm_missing_log_returns_zero(tmp_path: Path) -> None:
    from halyard.ai_log import confirm_session_attributions

    changed = confirm_session_attributions(tmp_path, [("some line", "acme:auth")])
    assert changed == 0


# ---------------------------------------------------------------------------
# interactive_confirm_attribution
# ---------------------------------------------------------------------------


def test_interactive_no_timeclock_exits_early(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from halyard.orchestration import interactive_confirm_attribution

    log = tmp_path / "ai-sessions.log"
    log.write_text(HEADER)
    append_session(tmp_path, _session(project=None))

    interactive_confirm_attribution(tmp_path)

    captured = capsys.readouterr()
    assert "timeclock" in captured.out.lower()


def test_interactive_no_candidates_exits_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from halyard.orchestration import interactive_confirm_attribution

    log = tmp_path / "ai-sessions.log"
    log.write_text(HEADER)
    # session is already attributed — no candidates
    append_session(tmp_path, _session(project="acme:auth"))

    tc = tmp_path / "time.timeclock"
    tc.write_text(
        "i 2026-05-07 09:00:00 acme:auth\no 2026-05-07 11:00:00\n"
    )

    interactive_confirm_attribution(tmp_path)

    captured = capsys.readouterr()
    assert "no unattributed" in captured.out.lower()


def test_interactive_confirms_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard.orchestration import interactive_confirm_attribution

    log = tmp_path / "ai-sessions.log"
    log.write_text(HEADER)
    sess = _session(start=datetime(2026, 5, 7, 10, 0), project=None, minutes=10)
    append_session(tmp_path, sess)

    tc = tmp_path / "time.timeclock"
    tc.write_text(
        "i 2026-05-07 09:00:00 acme:auth\no 2026-05-07 11:00:00\n"
    )

    monkeypatch.setattr("typer.prompt", lambda *_a, **_kw: "y")

    interactive_confirm_attribution(tmp_path)

    content = log.read_text()
    assert "project=acme:auth" in content


def test_interactive_rejects_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from halyard.orchestration import interactive_confirm_attribution

    log = tmp_path / "ai-sessions.log"
    log.write_text(HEADER)
    sess = _session(start=datetime(2026, 5, 7, 10, 0), project=None, minutes=10)
    append_session(tmp_path, sess)

    tc = tmp_path / "time.timeclock"
    tc.write_text(
        "i 2026-05-07 09:00:00 acme:auth\no 2026-05-07 11:00:00\n"
    )

    monkeypatch.setattr("typer.prompt", lambda *_a, **_kw: "n")

    interactive_confirm_attribution(tmp_path)

    content = log.read_text()
    assert "project=" not in content.replace("; Halyard", "")


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


def test_confirm_attribution_cli_no_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["confirm-attribution"])
    assert result.exit_code == 1
    assert "halyard init" in result.output
