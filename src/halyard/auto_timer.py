"""Auto human timer — records timeclock entries while Claude Code is active.

Presence-window model: one i/o timeclock block per contiguous work session,
regardless of how many AI turns it contains. A session is considered ended
when more than INACTIVITY_MINUTES have passed since the last recorded activity.

State file: ~/.halyard/auto-timer (key=value, same style as ~/.halyard/active)

  project=kormilo:halyard
  timeclock=/path/to/time.timeclock
  started=2026-05-09 14:23:00
  last_activity=2026-05-09 15:47:00

Timeclock entries written with a ;auto comment so they are distinguishable
from manual entries:

  i 2026-05-09 14:23:00 kormilo:halyard  ;auto
  o 2026-05-09 15:47:00
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

_AUTO_TIMER_FILE = Path.home() / ".halyard" / "auto-timer"
_INACTIVITY_MINUTES = 30
_TS_FMT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------


def _read_state() -> dict[str, str]:
    if not _AUTO_TIMER_FILE.exists():
        return {}
    return dict(
        line.split("=", 1) for line in _AUTO_TIMER_FILE.read_text().splitlines() if "=" in line
    )


def _write_state(state: dict[str, str]) -> None:
    _AUTO_TIMER_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AUTO_TIMER_FILE.write_text("".join(f"{k}={v}\n" for k, v in state.items()))


def _clear_state() -> None:
    _AUTO_TIMER_FILE.unlink(missing_ok=True)


def _write_clockout(timeclock: Path, ts: str) -> None:
    from halyard.ai_log import locked_file

    with locked_file(timeclock, "a") as f:
        f.write(f"o {ts}\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def auto_timer_close_if_stale(now: datetime | None = None) -> bool:
    """Close the auto-timer if last_activity is older than INACTIVITY_MINUTES.

    Returns True if a timer was closed, False otherwise.
    """
    state = _read_state()
    if not state:
        return False

    last_str = state.get("last_activity") or state.get("started", "")
    if not last_str:
        _clear_state()
        return False

    try:
        last = datetime.strptime(last_str, _TS_FMT)
    except ValueError:
        _clear_state()
        return False

    clock = now or datetime.now()
    elapsed = (clock - last).total_seconds() / 60
    if elapsed >= _INACTIVITY_MINUTES:
        tc_str = state.get("timeclock", "")
        if tc_str:
            tc = Path(tc_str)
            if tc.exists():
                _write_clockout(tc, last_str)
        _clear_state()
        return True

    return False


def auto_timer_activity(project: str, timeclock: Path, now: datetime | None = None) -> None:
    """Open the auto-timer if not running; otherwise update last_activity.

    Silently skips if a manual timer is already running.
    """
    from halyard.reports import read_active_timer

    if read_active_timer() is not None:
        return  # manual timer wins

    if not timeclock.exists():
        return

    clock = now or datetime.now()
    ts = clock.strftime(_TS_FMT)
    state = _read_state()

    if not state:
        # Open a new auto-timer: write clock-in entry then save state
        from halyard.ai_log import locked_file

        with locked_file(timeclock, "a") as f:
            f.write(f"i {ts} {project}  ;auto\n")

        _write_state(
            {
                "project": project,
                "timeclock": str(timeclock),
                "started": ts,
                "last_activity": ts,
            }
        )
    else:
        # Already open — just refresh last_activity
        state["last_activity"] = ts
        _write_state(state)


def auto_timer_update_activity(now: datetime | None = None) -> None:
    """Update last_activity without opening a new timer (called on Stop hook)."""
    state = _read_state()
    if not state:
        return
    clock = now or datetime.now()
    state["last_activity"] = clock.strftime(_TS_FMT)
    _write_state(state)


def auto_timer_close_now(now: datetime | None = None) -> bool:
    """Close the auto-timer immediately (called when the user runs timer stop).

    Returns True if a timer was closed, False if nothing was open.
    """
    state = _read_state()
    if not state:
        return False

    clock = now or datetime.now()
    ts = clock.strftime(_TS_FMT)
    tc_str = state.get("timeclock", "")
    if tc_str:
        tc = Path(tc_str)
        if tc.exists():
            _write_clockout(tc, ts)
    _clear_state()
    return True
