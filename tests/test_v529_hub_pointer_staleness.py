"""v5.29 — a stale hub pointer must be distinguishable from an unset one.

`find_hub()` returns None for both "never configured" and "configured but
the directory is gone". The second case silently diverts every ambient
session to ~/.halyard/unattributed.log while doctor reports "no hub
configured" — which is what made a live capture outage undiagnosable.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from halyard import hub as hub_mod
from halyard.ai_log import AI_LOG_FILENAME
from halyard.cli import app
from halyard.doctor import build_doctor_report
from halyard.hub import configured_hub_path, find_hub

runner = CliRunner()


def _write_pointer(target: Path) -> None:
    """Write the hub pointer file.

    conftest's autouse `_HUB_POINTER` override already redirects this off
    the real ~/.halyard; write through `_hub_pointer()` so these tests
    inherit that isolation. state_integrity mode is `off` by default, so
    the pointer is a plain file and no sidecar is needed.
    """
    pointer = hub_mod._hub_pointer()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(target) + "\n", encoding="utf-8")


def _make_hub(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "halyard.toml").write_text("[project]\nslug='h'\nname='H'\n", encoding="utf-8")
    (root / AI_LOG_FILENAME).write_text("; halyard\n", encoding="utf-8")
    return root


def _ids(report: object) -> set[str]:
    return {c.id for c in report.checks}  # type: ignore[attr-defined]


# --- the accessor -----------------------------------------------------


def test_configured_path_survives_a_missing_directory(tmp_path: Path) -> None:
    gone = tmp_path / "moved-away"  # deliberately never created
    _write_pointer(gone)
    assert configured_hub_path() == gone
    assert find_hub() is None, "find_hub keeps its contract — None means no usable hub"


def test_configured_path_is_none_without_a_pointer() -> None:
    assert configured_hub_path() is None
    assert find_hub() is None


def test_configured_path_matches_find_hub_when_valid(tmp_path: Path) -> None:
    hub = _make_hub(tmp_path / "hub")
    _write_pointer(hub)
    assert configured_hub_path() == hub
    assert find_hub() == hub


# --- the doctor check -------------------------------------------------


def test_stale_pointer_reports_hub_stale(tmp_path: Path) -> None:
    gone = tmp_path / "moved-away"
    _write_pointer(gone)
    check = next(c for c in build_doctor_report(tool="all").checks if c.id == "hub.stale")
    assert check.status == "error"
    assert str(gone) in check.detail
    assert "unattributed.log" in check.detail
    assert "recoverable" in check.detail  # must not imply data loss
    assert "halyard hub set" in (check.fix or "")


def test_stale_pointer_suppresses_the_unconfigured_check(tmp_path: Path) -> None:
    """The two ids are mutually exclusive — dashboard/TUI key off them."""
    _write_pointer(tmp_path / "moved-away")
    assert "hub.configured" not in _ids(build_doctor_report(tool="all"))


def test_no_pointer_still_reports_unconfigured() -> None:
    ids = _ids(build_doctor_report(tool="all"))
    assert "hub.configured" in ids
    assert "hub.stale" not in ids


def test_valid_hub_reports_neither(tmp_path: Path) -> None:
    _write_pointer(_make_hub(tmp_path / "hub"))
    ids = _ids(build_doctor_report(tool="all"))
    assert "hub.stale" not in ids
    assert "hub.configured" not in ids
    assert "hub.valid" in ids


# --- the CLI ----------------------------------------------------------


def test_hub_set_and_show_round_trip(tmp_path: Path) -> None:
    hub = _make_hub(tmp_path / "hub")
    assert runner.invoke(app, ["hub", "set", str(hub)]).exit_code == 0
    assert find_hub() == hub
    result = runner.invoke(app, ["hub", "show"])
    assert result.exit_code == 0
    # Rich hard-wraps long paths, so compare against unwrapped output.
    assert str(hub) in result.stdout.replace("\n", "")


def test_hub_set_rejects_a_non_project(tmp_path: Path) -> None:
    plain = tmp_path / "not-a-project"
    plain.mkdir()
    assert runner.invoke(app, ["hub", "set", str(plain)]).exit_code == 1
    assert find_hub() is None


def test_hub_show_flags_a_stale_pointer(tmp_path: Path) -> None:
    _write_pointer(tmp_path / "moved-away")
    result = runner.invoke(app, ["hub", "show"])
    assert result.exit_code == 1
    assert "configured but missing" in result.stdout


def test_no_bare_hub_command_shadows_the_subapp() -> None:
    """Regression: the original defect was that *both* registrations worked.

    cli_setup registered a `hub` command and cli.py then added the cli_hub
    sub-app under the same name; Typer silently kept the sub-app, so
    `halyard hub <path>` — the fix doctor printed — could never run.
    """
    assert not [c for c in app.registered_commands if c.name == "hub"], (
        "a bare `hub` command shadows the hub sub-app again"
    )
    names = {
        g.name or (g.typer_instance.info.name if g.typer_instance else None)
        for g in app.registered_groups
    }
    assert "hub" in names, "hub sub-app is not registered"
