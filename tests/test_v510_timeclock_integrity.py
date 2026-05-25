"""v5.10 — timeclock integrity: Hub presence persistence + repair tool."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from halyard.auto_timer import INACTIVITY_MINUTES, read_presence
from halyard.cli import app
from halyard.hub_server import HubServer
from halyard.timeclock_repair import counted_minutes, reconstruct_timeclock

_FMT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Part 1 — Hub auto-presence persistence + restart reconcile
# ---------------------------------------------------------------------------


@pytest.fixture()
def hub_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    (home / ".halyard").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("halyard.auto_timer._AUTO_TIMER_FILE", home / ".halyard" / "auto-timer")
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", home / ".halyard" / "active")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text("[business]\n")
    tc = project_dir / "time.timeclock"
    tc.write_text("; timeclock\n")
    return project_dir, tc, home


def _write_presence_file(home: Path, project: str, tc: Path, started: datetime, last: datetime):
    (home / ".halyard" / "auto-timer").write_text(
        f"project={project}\ntimeclock={tc}\n"
        f"started={started.strftime(_FMT)}\nlast_activity={last.strftime(_FMT)}\n"
    )


def test_reconcile_resumes_recent_window(hub_env):
    project_dir, tc, home = hub_env
    now = datetime.now()
    started = now - timedelta(minutes=10)
    last = now - timedelta(minutes=5)
    tc.write_text(f"; timeclock\ni {started.strftime(_FMT)} kormilo/halyard  ;auto\n")
    _write_presence_file(home, "kormilo/halyard", tc, started, last)

    server = HubServer(project_dir=project_dir, port=0)  # __init__ reconciles

    assert server.state.auto_project == "kormilo/halyard"
    assert server.state.auto_timeclock == tc
    # No new clock-out written; the file is preserved for the resumed window.
    assert "o " not in tc.read_text()
    assert read_presence() != {}


def test_reconcile_closes_stale_window(hub_env):
    project_dir, tc, home = hub_env
    now = datetime.now()
    started = now - timedelta(minutes=90)
    last = now - timedelta(minutes=INACTIVITY_MINUTES + 20)
    tc.write_text(f"; timeclock\ni {started.strftime(_FMT)} kormilo/halyard  ;auto\n")
    _write_presence_file(home, "kormilo/halyard", tc, started, last)

    server = HubServer(project_dir=project_dir, port=0)

    assert server.state.auto_project is None
    # The orphaned open is closed at its last known activity.
    assert f"o {last.strftime(_FMT)}" in tc.read_text()
    assert read_presence() == {}


def test_reconcile_clears_malformed_file(hub_env):
    project_dir, _tc, home = hub_env
    (home / ".halyard" / "auto-timer").write_text("garbage=value\n")

    server = HubServer(project_dir=project_dir, port=0)

    assert server.state.auto_project is None
    assert read_presence() == {}


def test_presence_persist_roundtrip(hub_env):
    project_dir, tc, _home = hub_env
    server = HubServer(project_dir=project_dir, port=0)
    t0 = datetime(2026, 5, 20, 10, 0, 0)

    server._record_presence_activity("kormilo/halyard", tc, now=t0)
    state = read_presence()
    assert state["project"] == "kormilo/halyard"
    assert state["started"] == t0.strftime(_FMT)
    assert tc.read_text().count("i ") == 1

    server._record_presence_activity("kormilo/halyard", tc, now=t0 + timedelta(minutes=5))
    # Still one clock-in; only last_activity advanced.
    assert tc.read_text().count("i ") == 1
    assert read_presence()["last_activity"] == (t0 + timedelta(minutes=5)).strftime(_FMT)

    server._close_presence_now(now=t0 + timedelta(minutes=10))
    assert read_presence() == {}
    assert "o 2026-05-20 10:10:00" in tc.read_text()


# ---------------------------------------------------------------------------
# Part 2 — reconstruction
# ---------------------------------------------------------------------------


def _pairs(lines: list[str]) -> list[tuple[str, str]]:
    out, open_ts = [], None
    for line in lines:
        p = line.split()
        if not p:
            continue
        if p[0] == "i":
            open_ts = f"{p[1]} {p[2]}"
        elif p[0] == "o" and open_ts is not None:
            out.append((open_ts, f"{p[1]} {p[2]}"))
            open_ts = None
    return out


def test_merges_auto_runs_within_window():
    lines = [
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto",
        "i 2026-05-20 10:10:00 kormilo/halyard  ;auto",
        "i 2026-05-20 10:25:00 kormilo/halyard  ;auto",
        "o 2026-05-20 10:30:00",
    ]
    out = reconstruct_timeclock(lines)
    assert _pairs(out) == [("2026-05-20 10:00:00", "2026-05-20 10:30:00")]


def test_splits_on_gap_over_window():
    lines = [
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto",
        "i 2026-05-20 10:10:00 kormilo/halyard  ;auto",
        "i 2026-05-20 11:00:00 kormilo/halyard  ;auto",  # 50-min gap
        "o 2026-05-20 11:05:00",
    ]
    out = reconstruct_timeclock(lines)
    assert _pairs(out) == [
        ("2026-05-20 10:00:00", "2026-05-20 10:10:00"),
        ("2026-05-20 11:00:00", "2026-05-20 11:05:00"),
    ]


def test_manual_entry_preserved_verbatim():
    lines = [
        "i 2026-05-07 20:08:08 kormilo:halyard",
        "o 2026-05-07 20:08:34",
    ]
    out = reconstruct_timeclock(lines)
    # Original colon-form i line kept exactly; o re-emitted at same timestamp.
    assert out[0] == "i 2026-05-07 20:08:08 kormilo:halyard"
    assert out[1] == "o 2026-05-07 20:08:34"


def test_backward_close_does_not_create_negative_window():
    lines = [
        "i 2026-05-20 12:00:00 kormilo/halyard  ;auto",
        "o 2026-05-09 14:00:00",  # 11 days in the past
    ]
    out = reconstruct_timeclock(lines)
    pairs = _pairs(out)
    assert pairs == [("2026-05-20 12:00:00", "2026-05-20 12:00:00")]
    assert counted_minutes(out) == 0.0


def test_far_future_close_is_not_billed():
    lines = [
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto",
        "i 2026-05-20 10:05:00 kormilo/halyard  ;auto",
        "o 2026-05-20 23:00:00",  # ~13h later: stale close, must not extend
    ]
    out = reconstruct_timeclock(lines)
    assert _pairs(out) == [("2026-05-20 10:00:00", "2026-05-20 10:05:00")]


def test_project_change_splits_window():
    lines = [
        "i 2026-05-20 10:00:00 acme/web  ;auto",
        "i 2026-05-20 10:10:00 kormilo/halyard  ;auto",
        "o 2026-05-20 10:15:00",
    ]
    out = reconstruct_timeclock(lines)
    # The acme window can't absorb a kormilo ping, so it closes at its own last
    # activity (no cross-project billing); kormilo runs to its clock-out.
    assert _pairs(out) == [
        ("2026-05-20 10:00:00", "2026-05-20 10:00:00"),
        ("2026-05-20 10:10:00", "2026-05-20 10:15:00"),
    ]


def test_orphan_close_dropped_and_header_preserved():
    lines = [
        "; Halyard timeclock",
        "o 2026-05-20 09:00:00",  # orphan, no open
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto",
        "o 2026-05-20 10:30:00",
    ]
    out = reconstruct_timeclock(lines)
    assert out[0] == "; Halyard timeclock"
    assert _pairs(out) == [("2026-05-20 10:00:00", "2026-05-20 10:30:00")]


def test_lone_trailing_open_left_open():
    # A single trailing clock-in (possibly a live window) is never given a
    # fabricated close — auto or manual.
    auto = reconstruct_timeclock(["i 2026-05-20 10:00:00 kormilo/halyard  ;auto"])
    assert auto == ["i 2026-05-20 10:00:00 kormilo/halyard  ;auto"]

    manual = reconstruct_timeclock(["i 2026-05-20 10:00:00 kormilo:halyard"])
    assert manual == ["i 2026-05-20 10:00:00 kormilo:halyard"]


def test_trailing_multi_ping_run_closed_at_last_activity():
    # A trailing run with dropped opens IS reconstructed: merged and closed at
    # the last activity ping (no explicit clock-out needed to trigger it).
    out = reconstruct_timeclock(
        [
            "i 2026-05-20 10:00:00 kormilo/halyard  ;auto",
            "i 2026-05-20 10:20:00 kormilo/halyard  ;auto",
            "i 2026-05-20 10:40:00 kormilo/halyard  ;auto",
        ]
    )
    assert _pairs(out) == [("2026-05-20 10:00:00", "2026-05-20 10:40:00")]


def test_already_clean_is_idempotent():
    lines = [
        "; header",
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto",
        "o 2026-05-20 10:30:00",
    ]
    assert reconstruct_timeclock(reconstruct_timeclock(lines)) == reconstruct_timeclock(lines)


def test_clean_multi_hour_window_not_crushed_on_rerun():
    # A long window built from sub-30-min pings survives a second pass: once the
    # pings are merged away its endpoints are >30 min apart, but a structurally
    # sound file must be left intact (regression: re-repair must not destroy it).
    corrupt = [
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto",
        "i 2026-05-20 10:25:00 kormilo/halyard  ;auto",
        "i 2026-05-20 10:50:00 kormilo/halyard  ;auto",
        "i 2026-05-20 11:15:00 kormilo/halyard  ;auto",
        "o 2026-05-20 11:30:00",
    ]
    once = reconstruct_timeclock(corrupt)
    assert _pairs(once) == [("2026-05-20 10:00:00", "2026-05-20 11:30:00")]
    assert counted_minutes(once) == 90.0
    twice = reconstruct_timeclock(once)
    assert twice == once
    assert counted_minutes(twice) == 90.0


def test_clean_window_survives_reconstruction_of_corrupt_tail():
    # A file with a legit multi-hour window AND a later dropped-open run: the
    # corruption triggers a full reconstruct, but the clean window's authoritative
    # clock-out must be trusted (not crushed by the stale-close cap).
    lines = [
        "i 2026-05-20 09:00:00 kormilo/halyard  ;auto",  # clean 3h window
        "o 2026-05-20 12:00:00",
        "i 2026-05-20 14:00:00 kormilo/halyard  ;auto",  # dropped-open run
        "i 2026-05-20 14:10:00 kormilo/halyard  ;auto",
        "o 2026-05-20 14:30:00",
    ]
    out = reconstruct_timeclock(lines)
    assert _pairs(out) == [
        ("2026-05-20 09:00:00", "2026-05-20 12:00:00"),  # preserved, not crushed
        ("2026-05-20 14:00:00", "2026-05-20 14:30:00"),
    ]
    assert counted_minutes(out) == 180.0 + 30.0


def test_stale_close_capped_only_with_intervening_pings():
    # With a dropped open present, the far-future stale close is still capped.
    corrupt = [
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto",
        "i 2026-05-20 10:05:00 kormilo/halyard  ;auto",
        "o 2026-05-20 23:00:00",
    ]
    out = reconstruct_timeclock(corrupt)
    assert _pairs(out) == [("2026-05-20 10:00:00", "2026-05-20 10:05:00")]


# ---------------------------------------------------------------------------
# Part 2 — CLI
# ---------------------------------------------------------------------------


def test_check_reports_anomalies(tmp_path: Path):
    tc = tmp_path / "time.timeclock"
    tc.write_text(
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto\n"
        "i 2026-05-20 10:10:00 kormilo/halyard  ;auto\n"
        "o 2026-05-20 10:30:00\n"
    )
    result = CliRunner().invoke(app, ["timeclock", "check", "--timeclock", str(tc)])
    assert result.exit_code == 0
    assert "dropped opens" in result.stdout
    assert "1" in result.stdout  # one dropped open


def test_repair_dry_run_does_not_write(tmp_path: Path):
    tc = tmp_path / "time.timeclock"
    body = (
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto\n"
        "i 2026-05-20 10:10:00 kormilo/halyard  ;auto\n"
        "o 2026-05-20 10:30:00\n"
    )
    tc.write_text(body)
    result = CliRunner().invoke(app, ["timeclock", "repair", "--timeclock", str(tc)])
    assert result.exit_code == 0
    assert "Dry run" in result.stdout
    assert tc.read_text() == body  # untouched


def test_repair_apply_writes_and_backs_up(tmp_path: Path):
    tc = tmp_path / "time.timeclock"
    tc.write_text(
        "i 2026-05-20 10:00:00 kormilo/halyard  ;auto\n"
        "i 2026-05-20 10:10:00 kormilo/halyard  ;auto\n"
        "i 2026-05-20 10:25:00 kormilo/halyard  ;auto\n"
        "o 2026-05-20 10:30:00\n"
    )
    result = CliRunner().invoke(app, ["timeclock", "repair", "--timeclock", str(tc), "--apply"])
    assert result.exit_code == 0
    assert _pairs(tc.read_text().splitlines()) == [("2026-05-20 10:00:00", "2026-05-20 10:30:00")]
    backups = list(tmp_path.glob("time.timeclock.bak-*"))
    assert len(backups) == 1
