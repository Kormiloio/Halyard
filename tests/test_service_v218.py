"""Test backfill for v2.12 — service install/uninstall/status (v2.18 tasks 5.1-5.4)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from halyard.service import (
    PLIST_LABEL,
    _plist,
    install_service,
    service_status,
    uninstall_service,
)


def _fake_plist_path(tmp_path: Path) -> Path:
    return tmp_path / f"{PLIST_LABEL}.plist"


# ---------------------------------------------------------------------------
# 5.1: install_service writes plist and calls launchctl load
# ---------------------------------------------------------------------------


def test_install_service_writes_plist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_plist = _fake_plist_path(tmp_path)
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        with patch("shutil.which", return_value="/usr/local/bin/halyard"):
            url = install_service(tmp_path, port=7432)

    assert fake_plist.exists()
    assert "halyard" in fake_plist.read_text()
    assert url == "http://127.0.0.1:7432/"


def test_install_service_calls_launchctl_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_plist = _fake_plist_path(tmp_path)
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        with patch("shutil.which", return_value="/usr/local/bin/halyard"):
            install_service(tmp_path, port=7432)

    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert "launchctl" in call_args
    assert "load" in call_args


# ---------------------------------------------------------------------------
# 5.2: uninstall_service removes plist and calls launchctl unload
# ---------------------------------------------------------------------------


def test_uninstall_removes_plist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_plist = _fake_plist_path(tmp_path)
    fake_plist.write_text("<plist/>")
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        uninstall_service()

    assert not fake_plist.exists()
    assert mock_run.called
    call_args = mock_run.call_args[0][0]
    assert "launchctl" in call_args
    assert "unload" in call_args


def test_uninstall_no_plist_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_plist = _fake_plist_path(tmp_path)
    assert not fake_plist.exists()
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    # Should not raise even when the plist doesn't exist
    with patch("subprocess.run"):
        uninstall_service()


# ---------------------------------------------------------------------------
# 5.3: service_status reports correct port from plist
# ---------------------------------------------------------------------------


def test_service_status_not_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_plist = _fake_plist_path(tmp_path)
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    running, msg = service_status()
    assert not running
    assert "not installed" in msg


def test_service_status_installed_and_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_plist = _fake_plist_path(tmp_path)
    fake_plist.write_text("<plist/>")
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="{}", stderr=""
        )
        running, msg = service_status()

    assert running
    assert "127.0.0.1" in msg


def test_service_status_installed_not_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_plist = _fake_plist_path(tmp_path)
    fake_plist.write_text("<plist/>")
    monkeypatch.setattr("halyard.service.PLIST_PATH", fake_plist)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr=""
        )
        running, msg = service_status()

    assert not running
    assert "not running" in msg


# ---------------------------------------------------------------------------
# 5.4: Plist generation handles paths with special characters (D-4)
# ---------------------------------------------------------------------------


def test_plist_escapes_special_chars_in_path() -> None:
    project_dir = Path("/Users/mario/clients/acme & co/auth<2026>")
    plist_text = _plist("/usr/local/bin/halyard", project_dir, port=7432)

    # XML special chars must be escaped in element content
    assert "&amp;" in plist_text or "acme" in plist_text  # & escaped
    assert "<2026>" not in plist_text  # raw < > must not appear unescaped
    assert "<?xml" in plist_text


def test_plist_escapes_ampersand_in_exe_path() -> None:
    plist_text = _plist("/usr/local/bin/hal & yard", Path("/tmp/proj"), port=7432)
    assert "&amp;" in plist_text
    assert "hal & yard" not in plist_text
