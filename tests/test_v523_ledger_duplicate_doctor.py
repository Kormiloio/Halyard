"""Tests for the v5.23 ledger duplicate canary in `halyard doctor`.

The v5.21 incident left ~447 byte-identical duplicate `s` rows in the repo
ledger (one gemini session re-appended 143 times by the 30-minute import
timer) while doctor reported all OK — read-time collapse hid the rows from
every report surface. These tests pin the canary that closes that blind
spot: byte-identical duplicate `s` lines and stalled same-job_id re-appends
are reported (warning, never error), with a suggested remediation. The
job_id signal counts *stalled* rows (no growth in end time or token total)
so the legitimate growth re-imports of a long-lived live session — verified
live: 48 advancing rows over a 3-day codex session — never fire it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME, AiSession
from halyard.doctor import (
    _DUP_JOB_STALLED_THRESHOLD,
    _ledger_duplicate_checks,
    build_doctor_report,
)

_BASE = datetime(2026, 6, 1, 9, 0, 0)


def _project(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "halyard.toml").write_text("[project]\n", encoding="utf-8")
    (path / AI_LOG_FILENAME).write_text("; header\n", encoding="utf-8")
    return path


def _line(
    *,
    minute: int,
    job_id: str | None = None,
    tool: str = "gemini-cli",
    tokens: int = 100,
    cost: float = 0.01,
) -> str:
    end = _BASE + timedelta(minutes=minute)
    return AiSession(
        start=_BASE - timedelta(minutes=5),
        end=end,
        tool=tool,
        model="gemini-2.5-pro",
        input_tokens=tokens,
        output_tokens=20,
        cost_usd=cost,
        project="acme:auth",
        job_id=job_id,
    ).to_log_line()


def _append(project: Path, lines: list[str]) -> None:
    with (project / AI_LOG_FILENAME).open("a", encoding="utf-8") as fh:
        fh.write("".join(line + "\n" for line in lines))


def _ledger_checks(project: Path) -> list:
    return _ledger_duplicate_checks(project, None)


def test_byte_identical_duplicates_warn(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    dup = _line(minute=0, job_id="gemini:abc123")
    _append(project, [dup] * 144 + [_line(minute=10)])

    checks = _ledger_checks(project)
    dup_check = next(c for c in checks if c.id.startswith("ledger.duplicates."))
    assert dup_check.status == "warning"
    assert "143 surplus" in dup_check.detail
    assert "1 distinct line(s)" in dup_check.detail
    assert "x144" in dup_check.detail
    assert dup_check.fix is not None
    assert "back up ai-sessions.log" in dup_check.fix
    assert "first occurrence" in dup_check.fix


def test_clean_ledger_no_checks(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    _append(
        project,
        [_line(minute=m, job_id=f"gemini:s{m}") for m in range(10)],
    )

    assert _ledger_checks(project) == []


def test_stalled_job_id_with_distinct_rows_warns(tmp_path: Path) -> None:
    # Rows differ byte-wise (cost varies) so byte-identity alone would
    # miss the loop; end time and tokens never advance, so every row
    # after the first is a stalled re-append and the job_id count fires.
    project = _project(tmp_path / "project")
    _append(
        project,
        [
            _line(minute=0, job_id="gemini:loop1", cost=0.01 + i * 0.001)
            for i in range(_DUP_JOB_STALLED_THRESHOLD + 1)
        ],
    )

    checks = _ledger_checks(project)
    assert not any(c.id.startswith("ledger.duplicates.") for c in checks)
    job_check = next(c for c in checks if c.id.startswith("ledger.job_rows."))
    assert job_check.status == "warning"
    assert "gemini:loop1" in job_check.detail
    assert f"x{_DUP_JOB_STALLED_THRESHOLD} stalled" in job_check.detail
    assert job_check.fix is not None
    assert "import timer" in job_check.fix


def test_growth_reimports_never_flagged(tmp_path: Path) -> None:
    # The live false positive this design avoids: a long-lived session
    # re-imported once per timer tick while its file grows. Every row
    # advances in end time and tokens — 50 rows, zero stalled.
    project = _project(tmp_path / "project")
    _append(
        project,
        [_line(minute=m, job_id="codex:live1", tokens=100 + m * 50) for m in range(50)],
    )

    assert _ledger_checks(project) == []


def test_below_threshold_stalls_are_quiet(tmp_path: Path) -> None:
    # A couple of stalled re-appends are legitimate (e.g. one re-import
    # after an import-state reset, as in the v5.21 repair).
    project = _project(tmp_path / "project")
    _append(
        project,
        [
            _line(minute=0, job_id="codex:reset1", cost=0.01 + i * 0.001)
            for i in range(_DUP_JOB_STALLED_THRESHOLD)  # threshold-1 stalled
        ],
    )

    assert _ledger_checks(project) == []


def test_project_and_hub_same_dir_scanned_once(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    _append(project, [_line(minute=0)] * 2)

    checks = _ledger_duplicate_checks(project, project)
    assert len([c for c in checks if c.id.startswith("ledger.duplicates.")]) == 1


def test_distinct_project_and_hub_both_scanned(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    hub = _project(tmp_path / "hub")
    _append(project, [_line(minute=0)] * 2)
    _append(hub, [_line(minute=5)] * 2)

    checks = _ledger_duplicate_checks(project, hub)
    assert len([c for c in checks if c.id.startswith("ledger.duplicates.")]) == 2


def test_non_session_lines_never_counted(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    _append(
        project,
        ["; a comment", "; a comment", "a deadbeef0000 project=x", "a deadbeef0000 project=x", ""],
    )

    assert _ledger_checks(project) == []


def test_missing_log_is_quiet(tmp_path: Path) -> None:
    project = tmp_path / "no-log"
    project.mkdir()

    assert _ledger_duplicate_checks(project, None) == []


def test_warning_never_error_in_full_report(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # The exit-code contract: duplicates degrade the file, not the reports,
    # so the canary must never push the doctor report to error. Identical
    # rows trip both signals (byte-identity and stalled job_id) at once.
    home = tmp_path / "home"
    project = _project(tmp_path / "project")
    monkeypatch.setattr(Path, "home", lambda: home)
    state = home / ".halyard"
    state.mkdir(parents=True, exist_ok=True)
    (state / "hub").write_text(str(project) + "\n", encoding="utf-8")
    _append(project, [_line(minute=0, job_id="gemini:loop1")] * 50)

    report = build_doctor_report(start=project)
    ledger_checks = [c for c in report.checks if c.id.startswith("ledger.")]
    assert len(ledger_checks) == 2, "expected both duplicate-canary signals to fire"
    assert all(c.status == "warning" for c in ledger_checks)
