"""v5.33 — recover timeclock hours the v5.26 defect already lost.

Before v5.26 the idle policy closed a window mid-turn and nothing could
reopen it, so hours of work Halyard *had already recorded as sessions* were
absent from the timeclock. v5.26 stops the bleeding for new sessions; this
reconciles historical days against the ledger, which is the evidence.

The dangerous failure here is double-billing, so most of these tests are
about what must *not* be proposed.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.cli import app
from halyard.timeclock_repair import counted_minutes, reconcile_from_sessions

runner = CliRunner()
TS = "%Y-%m-%d %H:%M:%S"


def _at(h: int, m: int = 0) -> datetime:
    return datetime(2026, 8, 11, h, m, 0)


def _lines(*pairs: tuple[datetime, datetime]) -> list[str]:
    out = ["; timeclock"]
    for start, end in pairs:
        out.append(f"i {start.strftime(TS)} acme:web  ;auto")
        out.append(f"o {end.strftime(TS)}")
    return out


def _session(start: datetime, end: datetime, project: str = "acme:web"):
    return (start, end, project)


# --- the observed day -------------------------------------------------


def test_recovers_the_lost_stretch(tmp_path: Path) -> None:
    """2026-08-11: timeclock had 16:12-16:31 and 18:24-18:41; the ledger
    proves a continuous session 16:31-18:32. The gap is recoverable."""
    lines = _lines((_at(16, 12), _at(16, 31)), (_at(18, 24), _at(18, 41)))
    assert counted_minutes(lines) == pytest.approx(36, abs=1)

    out, recovered, _skipped = reconcile_from_sessions(
        lines, [_session(_at(16, 12), _at(16, 31)), _session(_at(16, 31), _at(18, 32))]
    )

    assert recovered == pytest.approx(113, abs=1), "16:31->18:24 was missing"
    assert counted_minutes(out) == pytest.approx(149, abs=1)


# --- what must never be proposed --------------------------------------


def test_a_fully_covered_session_proposes_nothing(tmp_path: Path) -> None:
    lines = _lines((_at(9), _at(12)))
    out, recovered, _skipped = reconcile_from_sessions(lines, [_session(_at(10), _at(11))])
    assert recovered == 0.0
    assert out == lines


def test_overlapping_sessions_do_not_double_bill() -> None:
    """Two sessions covering the same wall-clock time bill it once.

    Coverage proposed for an earlier session must suppress the later one —
    this is the case that would silently inflate an invoice.
    """
    out, recovered, _skipped = reconcile_from_sessions(
        ["; timeclock"],
        [_session(_at(9), _at(11)), _session(_at(10), _at(12))],
    )
    assert recovered == pytest.approx(180, abs=1), "9->12 once, not 2h + 2h"
    assert counted_minutes(out) == pytest.approx(180, abs=1)


def test_identical_sessions_bill_once() -> None:
    out, recovered, _skipped = reconcile_from_sessions(
        ["; timeclock"], [_session(_at(9), _at(11)), _session(_at(9), _at(11))]
    )
    assert recovered == pytest.approx(120, abs=1)
    assert counted_minutes(out) == pytest.approx(120, abs=1)


def test_it_is_idempotent() -> None:
    """Re-running after --apply must propose nothing further."""
    first, recovered, _s1 = reconcile_from_sessions(["; timeclock"], [_session(_at(9), _at(11))])
    assert recovered > 0

    second, again, _s2 = reconcile_from_sessions(first, [_session(_at(9), _at(11))])

    assert again == 0.0
    assert second == first


def test_partial_coverage_recovers_only_the_gap() -> None:
    lines = _lines((_at(9), _at(10)))
    _out, recovered, _skipped = reconcile_from_sessions(lines, [_session(_at(9), _at(12))])
    assert recovered == pytest.approx(120, abs=1), "only 10->12 was missing"


def test_nothing_is_proposed_outside_a_session() -> None:
    """The session bounds the claim — idle between sessions stays unbilled."""
    _out, recovered, _skipped = reconcile_from_sessions(
        ["; timeclock"], [_session(_at(9), _at(10)), _session(_at(15), _at(16))]
    )
    assert recovered == pytest.approx(120, abs=1), "the 10->15 idle is not work"


def test_an_open_entry_does_not_suppress_recovery() -> None:
    """A forgotten clock-in has no end, so it proves coverage of nothing.

    Treating it as covering "until now" would let one stale open entry
    silently block every later recovery.
    """
    lines = ["; timeclock", f"i {_at(8).strftime(TS)} acme:web  ;auto"]
    _out, recovered, _skipped = reconcile_from_sessions(lines, [_session(_at(9), _at(11))])
    assert recovered == pytest.approx(120, abs=1)


def test_history_is_appended_never_rewritten() -> None:
    lines = _lines((_at(9), _at(10)))
    out, _r, _s = reconcile_from_sessions(lines, [_session(_at(9), _at(12))])
    assert out[: len(lines)] == lines


def test_backwards_sessions_are_ignored() -> None:
    out, recovered, _skipped = reconcile_from_sessions(["; timeclock"], [_session(_at(11), _at(9))])
    assert recovered == 0.0
    assert out == ["; timeclock"]


# --- the CLI safety contract ------------------------------------------


def _project(tmp_path: Path) -> Path:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "ai-sessions.log").write_text(
        "; halyard\n"
        f"s {_at(16, 31).strftime('%Y-%m-%dT%H:%M:%S')} "
        f"{_at(18, 32).strftime('%Y-%m-%dT%H:%M:%S')} "
        "claude-code claude-opus-5 100 50 0.0 project=acme:web\n",
        encoding="utf-8",
    )
    tc = tmp_path / "time.timeclock"
    tc.write_text("\n".join(_lines((_at(16, 12), _at(16, 31)))) + "\n", encoding="utf-8")
    return tc


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tc = _project(tmp_path)
    before = tc.read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["timeclock", "repair", "--from-sessions"])

    assert result.exit_code == 0
    assert tc.read_text(encoding="utf-8") == before, "dry run must not write"
    assert "Dry run" in result.stdout


def test_apply_backs_up_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tc = _project(tmp_path)
    before = tc.read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["timeclock", "repair", "--from-sessions", "--apply"])

    assert result.exit_code == 0
    backups = list(tmp_path.glob("time.timeclock.bak-*"))
    assert len(backups) == 1, "a timestamped backup must exist before any write"
    assert backups[0].read_text(encoding="utf-8") == before
    assert counted_minutes(tc.read_text(encoding="utf-8").splitlines()) > counted_minutes(
        before.splitlines()
    )


def test_a_clean_timeclock_reports_and_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (tmp_path / "ai-sessions.log").write_text("; halyard\n", encoding="utf-8")
    tc = tmp_path / "time.timeclock"
    tc.write_text("; timeclock\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["timeclock", "repair", "--from-sessions"])

    assert result.exit_code == 0
    assert "already covers" in result.stdout


def test_an_implausibly_long_session_is_skipped() -> None:
    """A 27-day Codex rollout is a background process, not 27 days of work.

    The collectors cap a live session at 12 h; a row past that is, by the
    codebase's own standard, not one sitting. On the machine that motivated
    this, two such sessions were 89% of all session time and would have
    proposed 647 h of "human time".
    """
    long_start = datetime(2026, 8, 9, 13, 4)
    long_end = datetime(2026, 9, 5, 18, 28)

    out, recovered, skipped = reconcile_from_sessions(
        ["; timeclock"], [(long_start, long_end, "acme:web")]
    )

    assert recovered == 0.0
    assert skipped / 60 == pytest.approx(653, abs=1)
    assert out == ["; timeclock"]


def test_a_session_at_exactly_the_cap_still_counts() -> None:
    """12 h is the collectors' own limit, so it is plausible, not excluded."""
    start = datetime(2026, 8, 11, 8, 0)
    end = datetime(2026, 8, 11, 20, 0)

    _out, recovered, skipped = reconcile_from_sessions(["; timeclock"], [(start, end, "acme:web")])

    assert recovered == pytest.approx(720, abs=1)
    assert skipped == 0.0


def test_short_sessions_still_recover_alongside_a_skipped_one() -> None:
    """One implausible row must not suppress the legitimate ones."""
    _out, recovered, skipped = reconcile_from_sessions(
        ["; timeclock"],
        [
            (datetime(2026, 8, 9, 13, 4), datetime(2026, 9, 5, 18, 28), "acme:web"),
            (_at(9), _at(11), "acme:web"),
        ],
    )

    assert recovered == pytest.approx(120, abs=1)
    assert skipped > 0
