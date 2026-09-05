"""v5.31 — a lost hub response must not report a successful start as a failure.

`hub_server._handle_timer_action` writes the clock-in entry and
~/.halyard/active *before* it sends its response. A dropped connection
(ConnectionAbortedError out of _respond_json) therefore leaves a committed
timer behind while hub_client._request returns None — indistinguishable from
"the hub was never reachable". Falling through to _start_timer_local then
finds the hub's own write and raises TimerAlreadyRunning.

Surfaced as a Windows CI flake that "passed on re-run"; it is a real race,
and Windows only makes it likely enough to catch.

These tests drive the two halves deterministically — no threads, no sockets
torn down mid-write — by choosing what the hub and the disk report.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from halyard import hub_client, orchestration
from halyard.orchestration import TimerAlreadyRunning, start_timer, stop_timer


@pytest.fixture()
def committed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A project with a timer already committed to disk, as the hub leaves it."""
    home = tmp_path / "home"
    (home / ".halyard").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    active = home / ".halyard" / "active"
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)
    monkeypatch.setattr("halyard.orchestration._reports_mod._HALYARD_ACTIVE", active)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (project_dir / "time.timeclock").write_text("; timeclock\n", encoding="utf-8")

    # Commit the timer the way the hub does, before any response is sent.
    start_timer(project_dir, "acme:auth", direct=True)
    assert active.exists()
    return project_dir, active


def _lost_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """hub_client.start_timer returns None, exactly as a dropped response does."""
    monkeypatch.setattr(hub_client, "start_timer", lambda project_dir, project: None)


def test_lost_response_adopts_the_committed_timer(
    committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression: the user's own successful start must not be an error."""
    project_dir, _ = committed
    _lost_response(monkeypatch)
    monkeypatch.setattr(hub_client, "read_state", lambda: {"project": "acme:auth"})

    timer = start_timer(project_dir, "acme:auth")

    assert timer.slug == "acme:auth"


def test_unreachable_hub_still_raises(committed, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreachable hub vouches for nothing.

    This is what stops a stale active file from a crashed run being silently
    adopted — the failure mode that makes the loud, wrong error preferable.
    """
    project_dir, _ = committed
    _lost_response(monkeypatch)
    monkeypatch.setattr(hub_client, "read_state", lambda: None)

    with pytest.raises(TimerAlreadyRunning):
        start_timer(project_dir, "acme:auth")


def test_hub_naming_a_different_project_does_not_adopt(
    committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hub and disk must agree; disagreement is stranger than a dropped response."""
    project_dir, _ = committed
    _lost_response(monkeypatch)
    monkeypatch.setattr(hub_client, "read_state", lambda: {"project": "globex:reports"})

    with pytest.raises(TimerAlreadyRunning):
        start_timer(project_dir, "acme:auth")


def test_hub_reporting_no_timer_does_not_adopt(committed, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir, _ = committed
    _lost_response(monkeypatch)
    monkeypatch.setattr(hub_client, "read_state", lambda: {"project": None})

    with pytest.raises(TimerAlreadyRunning):
        start_timer(project_dir, "acme:auth")


def test_adopted_timer_reports_its_real_start_not_a_reset_clock(
    committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong start time is harder to notice than a wrong error, and it bills."""
    project_dir, _active = committed
    on_disk = orchestration._reports_mod.read_active_timer(prefer_hub=False)
    assert on_disk is not None

    _lost_response(monkeypatch)
    monkeypatch.setattr(hub_client, "read_state", lambda: {"project": "acme:auth"})

    timer = start_timer(project_dir, "acme:auth")

    assert timer.started == on_disk.started
    assert timer.timeclock == on_disk.timeclock


def test_adoption_does_not_write_a_second_clock_in(
    committed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adopting is a read, not a start — the timeclock must not grow."""
    project_dir, _ = committed
    timeclock = project_dir / "time.timeclock"
    before = timeclock.read_text(encoding="utf-8")

    _lost_response(monkeypatch)
    monkeypatch.setattr(hub_client, "read_state", lambda: {"project": "acme:auth"})
    start_timer(project_dir, "acme:auth")

    assert timeclock.read_text(encoding="utf-8") == before


def test_direct_path_is_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """direct=True is the hub's own path; it must never consult the hub."""
    home = tmp_path / "home"
    (home / ".halyard").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    active = home / ".halyard" / "active"
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active)
    monkeypatch.setattr("halyard.orchestration._reports_mod._HALYARD_ACTIVE", active)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text("[business]\n", encoding="utf-8")
    (project_dir / "time.timeclock").write_text("; timeclock\n", encoding="utf-8")

    def _boom():  # pragma: no cover - must not be reached
        raise AssertionError("direct=True consulted the hub")

    monkeypatch.setattr(hub_client, "read_state", _boom)

    start_timer(project_dir, "acme:auth", direct=True)
    with pytest.raises(TimerAlreadyRunning):
        start_timer(project_dir, "acme:auth", direct=True)

    stop_timer(project_dir, direct=True)
