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
# Canonical auto-timer idle policy; the Hub derives its timedelta from this.
INACTIVITY_MINUTES = 30
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


# ---------------------------------------------------------------------------
# Shared presence-state API (used by the Hub so its in-memory auto-presence
# survives a restart — the file is the single source of truth shared by the
# Hub and this standalone path).
# ---------------------------------------------------------------------------


def write_presence(
    project: str, timeclock: Path, started: datetime, last_activity: datetime
) -> None:
    """Persist the open auto-presence window to ``~/.halyard/auto-timer``."""
    _write_state(
        {
            "project": project,
            "timeclock": str(timeclock),
            "started": started.strftime(_TS_FMT),
            "last_activity": last_activity.strftime(_TS_FMT),
        }
    )


def read_presence() -> dict[str, str]:
    """Return the persisted auto-presence window, or ``{}`` if none."""
    return _read_state()


def clear_presence() -> None:
    """Delete the persisted auto-presence window."""
    _clear_state()


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
    hub_result = _try_hub_presence("close_stale", now=now)
    if hub_result is not None:
        return bool(hub_result.get("closed"))

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
    if elapsed >= INACTIVITY_MINUTES:
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
    from halyard.ai_log import _safe_field
    from halyard.reports import read_active_timer

    # Sanitize: a slug with whitespace/newline would corrupt the
    # space-delimited timeclock record.
    project = _safe_field(project)

    if read_active_timer() is not None:
        return  # manual timer wins

    if not timeclock.exists():
        return

    clock = now or datetime.now()
    ts = clock.strftime(_TS_FMT)
    if _try_hub_presence("activity", project=project, timeclock=timeclock, now=clock) is not None:
        return

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
    if _try_hub_presence("update", now=now) is not None:
        return

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
    hub_result = _try_hub_presence("close_now", now=now)
    if hub_result is not None:
        return bool(hub_result.get("closed"))

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


def safe_auto_timer_close() -> None:
    """Close the auto-timer, never raising into the caller.

    Used by `timer stop` paths: a corrupt timeclock must not abort the
    stop command, but the failure is logged (not silently swallowed) so
    it is diagnosable.
    """
    try:
        auto_timer_close_now()
    except Exception as exc:  # must not break the stop command
        from halyard.ai_log import _log_error

        _log_error("auto-timer close failed", exc)


def _try_hub_presence(
    action: str,
    *,
    project: str | None = None,
    timeclock: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object] | None:
    from halyard.hub_client import update_presence

    return update_presence(
        action,
        project=project,
        timeclock=timeclock,
        now=now.isoformat() if now else None,
    )
