"""Tests for `halyard start` / `halyard stop` (task 3.1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from halyard.cli import _HALYARD_ACTIVE, app

runner = CliRunner()

TIMECLOCK_HEADER = "; Halyard timeclock — hledger-compatible\n"


@pytest.fixture(autouse=True)
def clean_active(tmp_path: Path) -> None:  # type: ignore[misc]
    """Ensure no leftover active file bleeds between tests."""
    _HALYARD_ACTIVE.unlink(missing_ok=True)
    yield  # type: ignore[misc]
    _HALYARD_ACTIVE.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# halyard start
# ---------------------------------------------------------------------------


def test_start_writes_i_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "time.timeclock").write_text(TIMECLOCK_HEADER)

    result = runner.invoke(app, ["start", "acme/auth-migration"])

    assert result.exit_code == 0, result.output
    lines = (tmp_path / "time.timeclock").read_text().splitlines()
    i_lines = [l for l in lines if l.startswith("i ")]
    assert len(i_lines) == 1
    assert "acme:auth-migration" in i_lines[0]


def test_start_creates_active_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "time.timeclock").write_text(TIMECLOCK_HEADER)

    runner.invoke(app, ["start", "acme/auth-migration"])

    assert _HALYARD_ACTIVE.exists()
    content = _HALYARD_ACTIVE.read_text()
    assert "acme:auth-migration" in content
    assert "timeclock=" in content
    assert "started=" in content


def test_start_no_timeclock_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["start", "acme/auth-migration"])

    assert result.exit_code == 1
    assert "halyard init" in result.output


def test_start_while_active_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "time.timeclock").write_text(TIMECLOCK_HEADER)

    runner.invoke(app, ["start", "acme/auth-migration"])
    result = runner.invoke(app, ["start", "globex/new-work"])

    assert result.exit_code == 1
    assert "already running" in result.output


def test_start_bad_slug_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "time.timeclock").write_text(TIMECLOCK_HEADER)

    for bad in ("acme", "/auth-migration", "acme/"):
        result = runner.invoke(app, ["start", bad])
        assert result.exit_code == 1, f"expected failure for slug {bad!r}"


# ---------------------------------------------------------------------------
# halyard stop
# ---------------------------------------------------------------------------


def test_stop_writes_o_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "time.timeclock").write_text(TIMECLOCK_HEADER)

    runner.invoke(app, ["start", "acme/auth-migration"])
    result = runner.invoke(app, ["stop"])

    assert result.exit_code == 0, result.output
    lines = (tmp_path / "time.timeclock").read_text().splitlines()
    o_lines = [l for l in lines if l.startswith("o ")]
    assert len(o_lines) == 1


def test_stop_clears_active_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "time.timeclock").write_text(TIMECLOCK_HEADER)

    runner.invoke(app, ["start", "acme/auth-migration"])
    runner.invoke(app, ["stop"])

    assert not _HALYARD_ACTIVE.exists()


def test_stop_no_active_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = runner.invoke(app, ["stop"])

    assert result.exit_code == 1
    assert "No active timer" in result.output


def test_start_stop_timeclock_is_hledger_compatible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The i/o lines must match hledger timeclock format exactly."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "time.timeclock").write_text(TIMECLOCK_HEADER)

    runner.invoke(app, ["start", "acme/auth-migration"])
    runner.invoke(app, ["stop"])

    lines = [l for l in (tmp_path / "time.timeclock").read_text().splitlines() if l and not l.startswith(";")]
    assert lines[0].startswith("i ")
    parts_i = lines[0].split()
    assert parts_i[0] == "i"
    assert len(parts_i[1]) == 10  # YYYY-MM-DD
    assert len(parts_i[2]) == 8   # HH:MM:SS
    assert parts_i[3] == "acme:auth-migration"

    assert lines[1].startswith("o ")
    parts_o = lines[1].split()
    assert parts_o[0] == "o"
    assert len(parts_o[1]) == 10
    assert len(parts_o[2]) == 8
