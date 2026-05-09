"""Tests for halyard.service — macOS LaunchAgent management."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from halyard.service import uninstall_service

# ---------------------------------------------------------------------------
# L-2: launchctl unload must warn on non-zero exit code (not silently fail)
# ---------------------------------------------------------------------------


def test_uninstall_service_warns_on_launchctl_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If launchctl unload fails, a warning must be printed to stderr."""
    # Redirect PLIST_PATH to a temp location so the real plist is never touched
    fake_plist = tmp_path / "io.kormilo.halyard.plist"
    fake_plist.write_text("<plist/>")
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    # Simulate launchctl returning non-zero (service already stopped)
    def _failing_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="Could not find specified service",
        )

    monkeypatch.setattr(subprocess, "run", _failing_run)

    uninstall_service()

    captured = capsys.readouterr()
    assert "Warning" in captured.err
    assert "1" in captured.err  # return code in warning message


def test_uninstall_service_still_removes_plist_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when launchctl fails, the plist file must still be removed."""
    fake_plist = tmp_path / "io.kormilo.halyard.plist"
    fake_plist.write_text("<plist/>")
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    def _failing_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="error")

    monkeypatch.setattr(subprocess, "run", _failing_run)

    uninstall_service()

    assert not fake_plist.exists()


def test_uninstall_service_no_warning_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A successful launchctl unload must not print any warning."""
    fake_plist = tmp_path / "io.kormilo.halyard.plist"
    fake_plist.write_text("<plist/>")
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    def _ok_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _ok_run)

    uninstall_service()

    captured = capsys.readouterr()
    assert "Warning" not in captured.err


def test_uninstall_service_noop_when_plist_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the plist doesn't exist, uninstall_service must be a no-op."""
    fake_plist = tmp_path / "io.kormilo.halyard.plist"
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    mock_run = MagicMock()
    monkeypatch.setattr(subprocess, "run", mock_run)

    uninstall_service()

    mock_run.assert_not_called()
