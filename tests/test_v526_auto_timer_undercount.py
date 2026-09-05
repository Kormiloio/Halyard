"""v5.26 — the auto-timer measured prompt cadence, not work.

The idle policy closes a window retroactively at ``last_activity``, so a
single prompt kicking off a two-hour agent turn was closed out from under
itself at ~30 minutes. ``auto_timer_update_activity`` cannot rescue that: it
returns early when no window is open, which is exactly the state the stale
close leaves behind. It can refresh, never reopen or backfill.

Observed 2026-08-11: 34 minutes counted for a day whose own session log
proves 2h20m — a ~4x under-count in the feature whose purpose is billing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.auto_timer import _uncovered_spans, auto_timer_cover_session
from halyard.timeclock_repair import counted_minutes

TS = "%Y-%m-%d %H:%M:%S"


@pytest.fixture()
def clock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project timeclock, with no manual timer running."""
    home = tmp_path / "home"
    (home / ".halyard").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", home / ".halyard" / "active")
    tc = tmp_path / "time.timeclock"
    tc.write_text("; timeclock\n", encoding="utf-8")
    return tc


def _at(h: int, m: int) -> datetime:
    return datetime(2026, 8, 11, h, m, 0)


def _write(tc: Path, *pairs: tuple[datetime, datetime | None]) -> None:
    out = ["; timeclock\n"]
    for start, end in pairs:
        out.append(f"i {start.strftime(TS)} acme:web  ;auto\n")
        if end is not None:
            out.append(f"o {end.strftime(TS)}\n")
    tc.write_text("".join(out), encoding="utf-8")


# --- the observed failure ---------------------------------------------


def test_a_long_turn_after_one_prompt_is_counted(clock: Path) -> None:
    """The 2026-08-11 case: 16:12 -> 18:32 counted as 34m, not 2h20m.

    The stale close cut the window at 16:31; the session ran to 18:32.
    """
    _write(clock, (_at(16, 12), _at(16, 31)))
    assert counted_minutes(clock.read_text().splitlines()) == pytest.approx(19, abs=1)

    added = auto_timer_cover_session("acme:web", clock, _at(16, 31), _at(18, 32))

    assert added == pytest.approx(121, abs=1)
    total = counted_minutes(clock.read_text().splitlines())
    assert total == pytest.approx(140, abs=1), "should be ~2h20m, not ~19m"


def test_coverage_never_extends_past_the_session_end(clock: Path) -> None:
    """The session bounds the claim — coverage stops where evidence stops."""
    auto_timer_cover_session("acme:web", clock, _at(9, 0), _at(9, 30))
    assert counted_minutes(clock.read_text().splitlines()) == pytest.approx(30, abs=1)


def test_replaying_a_stop_adds_nothing(clock: Path) -> None:
    """Idempotent: a covered span must never be billed twice."""
    auto_timer_cover_session("acme:web", clock, _at(9, 0), _at(11, 0))
    first = counted_minutes(clock.read_text().splitlines())

    added = auto_timer_cover_session("acme:web", clock, _at(9, 0), _at(11, 0))

    assert added == 0.0
    assert counted_minutes(clock.read_text().splitlines()) == first


def test_a_fully_covered_span_writes_nothing(clock: Path) -> None:
    _write(clock, (_at(9, 0), _at(12, 0)))
    before = clock.read_text()

    assert auto_timer_cover_session("acme:web", clock, _at(10, 0), _at(11, 0)) == 0.0
    assert clock.read_text() == before


def test_only_the_gap_is_added_not_the_whole_span(clock: Path) -> None:
    """Union, not sum — overlapping windows must not double-bill."""
    _write(clock, (_at(9, 0), _at(10, 0)))

    added = auto_timer_cover_session("acme:web", clock, _at(9, 0), _at(11, 0))

    assert added == pytest.approx(60, abs=1), "only 10:00-11:00 was missing"
    assert counted_minutes(clock.read_text().splitlines()) == pytest.approx(120, abs=1)


def test_a_manual_timer_wins(clock: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same precedence as auto_timer_activity — never fight a manual timer."""
    monkeypatch.setattr("halyard.reports.read_active_timer", lambda *a, **k: object())
    before = clock.read_text()

    assert auto_timer_cover_session("acme:web", clock, _at(9, 0), _at(11, 0)) == 0.0
    assert clock.read_text() == before


def test_a_backwards_or_empty_span_writes_nothing(clock: Path) -> None:
    before = clock.read_text()
    assert auto_timer_cover_session("acme:web", clock, _at(11, 0), _at(9, 0)) == 0.0
    assert auto_timer_cover_session("acme:web", clock, _at(9, 0), _at(9, 0)) == 0.0
    assert clock.read_text() == before


def test_idle_between_sessions_is_not_claimed(clock: Path) -> None:
    """Coverage is per-session; the gap between two sessions stays unbilled."""
    auto_timer_cover_session("acme:web", clock, _at(9, 0), _at(10, 0))
    auto_timer_cover_session("acme:web", clock, _at(15, 0), _at(16, 0))

    assert counted_minutes(clock.read_text().splitlines()) == pytest.approx(120, abs=1)


def test_history_is_never_rewritten(clock: Path) -> None:
    """Append-only: rewriting user time data on a hook path is indefensible."""
    _write(clock, (_at(9, 0), _at(10, 0)))
    before = clock.read_text()

    auto_timer_cover_session("acme:web", clock, _at(9, 30), _at(11, 0))

    assert clock.read_text().startswith(before), "existing lines must be untouched"


def test_coverage_is_independent_of_presence_state(
    clock: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Hub must not be able to defeat this by closing the window first.

    The design assumed the fix would have to be mirrored in ``hub_server``,
    because the Hub applies the idle policy independently and wins on any
    machine running The Bridge. It does not: coverage is asserted against
    the timeclock *file*, not the presence state machine, so a window the
    Hub already closed mid-turn is still recovered. Pinned here because a
    future refactor routing coverage through presence would silently
    reintroduce the bug on exactly the machines that had it.
    """
    calls: list[str] = []

    def _boom(action: str, **kw: object) -> None:
        calls.append(action)
        raise AssertionError("coverage must not consult hub presence")

    monkeypatch.setattr("halyard.auto_timer._try_hub_presence", _boom)
    monkeypatch.setattr("halyard.auto_timer._read_state", dict)

    # The Hub closed the window at 16:31; the turn ran to 18:32.
    _write(clock, (_at(16, 12), _at(16, 31)))
    added = auto_timer_cover_session("acme:web", clock, _at(16, 31), _at(18, 32))

    assert not calls
    assert added == pytest.approx(121, abs=1)


# --- the interval arithmetic, on its own ------------------------------


@pytest.mark.parametrize(
    ("covered", "expected"),
    [
        ([], [(9, 12)]),
        ([(9, 12)], []),
        ([(9, 10)], [(10, 12)]),
        ([(11, 12)], [(9, 11)]),
        ([(10, 11)], [(9, 10), (11, 12)]),
        ([(8, 10)], [(10, 12)]),
        ([(11, 13)], [(9, 11)]),
        ([(8, 13)], []),
        ([(9, 10), (10, 11)], [(11, 12)]),
        ([(10, 11), (9, 10)], [(11, 12)]),  # unsorted input
    ],
)
def test_uncovered_spans(covered, expected) -> None:
    base = datetime(2026, 8, 11)
    hrs = lambda h: base + timedelta(hours=h)  # noqa: E731
    got = _uncovered_spans(hrs(9), hrs(12), [(hrs(a), hrs(b)) for a, b in covered])
    assert got == [(hrs(a), hrs(b)) for a, b in expected]
