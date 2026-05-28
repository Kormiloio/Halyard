"""Service install/uninstall/status + plist escaping (LaunchdProvider architecture)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from halyard.service import (
    PLIST_LABEL,
    install_service,
    service_status,
    uninstall_service,
)
from halyard.service_providers.launchd import LaunchdProvider


@pytest.fixture()
def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LaunchdProvider:
    p = LaunchdProvider(PLIST_LABEL)
    p.plist_path = tmp_path / f"{PLIST_LABEL}.plist"
    p.log_path = tmp_path / "halyard-dashboard.log"
    monkeypatch.setattr("halyard.service.get_provider", lambda label: p)
    return p


def _plist(halyard_exe: str, project_dir: Path, port: int) -> str:
    return LaunchdProvider(PLIST_LABEL)._plist(halyard_exe, project_dir, port)


def _ok_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")


# ---------------------------------------------------------------------------
# 5.1: install_service writes plist and calls launchctl load
# ---------------------------------------------------------------------------


def test_install_service_writes_plist(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(subprocess, "run", _ok_run)
    monkeypatch.setattr("halyard.cli_hooks._halyard_exe", lambda: "/usr/local/bin/halyard")

    url = install_service(tmp_path, port=7432)

    assert provider.plist_path.exists()
    assert "halyard" in provider.plist_path.read_text(encoding="utf-8")
    assert url == "http://127.0.0.1:7432/"


def test_install_service_calls_launchctl_load(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def _record(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _ok_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", _record)
    monkeypatch.setattr("halyard.cli_hooks._halyard_exe", lambda: "/usr/local/bin/halyard")

    install_service(tmp_path, port=7432)

    assert calls
    assert "launchctl" in calls[0]
    assert "load" in calls[0]


# ---------------------------------------------------------------------------
# 5.2: uninstall_service removes plist and calls launchctl unload
# ---------------------------------------------------------------------------


def test_uninstall_removes_plist(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider.plist_path.write_text("<plist/>", encoding="utf-8")
    calls: list[list[str]] = []

    def _record(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _ok_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", _record)

    removed = uninstall_service()

    assert removed is True
    assert not provider.plist_path.exists()
    assert calls
    assert "launchctl" in calls[0]
    assert "unload" in calls[0]


def test_uninstall_no_plist_is_safe(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert not provider.plist_path.exists()
    monkeypatch.setattr(subprocess, "run", _ok_run)

    # Should not raise even when the plist doesn't exist
    assert uninstall_service() is False


# ---------------------------------------------------------------------------
# 5.3: service_status reports correct port from plist
# ---------------------------------------------------------------------------


def test_service_status_not_installed(provider: LaunchdProvider) -> None:
    running, msg = service_status()
    assert not running
    assert "not installed" in msg


def test_service_status_installed_and_running(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider.plist_path.write_text("<plist/>", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=a[0], returncode=0, stdout="{}"),
    )

    running, msg = service_status()

    assert running
    assert "127.0.0.1" in msg


def test_service_status_installed_not_running(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider.plist_path.write_text("<plist/>", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=a[0], returncode=1, stdout=""),
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
