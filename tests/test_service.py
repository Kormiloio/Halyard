"""Tests for halyard service management (macOS LaunchAgent via LaunchdProvider)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from halyard.service import PLIST_LABEL, install_service, service_status, uninstall_service
from halyard.service_providers.launchd import LaunchdProvider


@pytest.fixture()
def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LaunchdProvider:
    """A LaunchdProvider redirected at a temp plist, wired into the service shim.

    Patching ``halyard.service.get_provider`` makes install_service /
    uninstall_service / service_status delegate to this instance, so the real
    ~/Library/LaunchAgents plist is never touched.
    """
    p = LaunchdProvider(PLIST_LABEL)
    p.plist_path = tmp_path / f"{PLIST_LABEL}.plist"
    p.log_path = tmp_path / "halyard-dashboard.log"
    monkeypatch.setattr("halyard.service.get_provider", lambda label: p)
    return p


# ---------------------------------------------------------------------------
# L-2: launchctl unload must warn on non-zero exit code (not silently fail)
# ---------------------------------------------------------------------------


def test_uninstall_service_warns_on_launchctl_failure(
    provider: LaunchdProvider,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """If launchctl unload fails, a warning must be printed to stderr."""
    provider.plist_path.write_text("<plist/>")

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
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even when launchctl fails, the plist file must still be removed."""
    provider.plist_path.write_text("<plist/>")

    def _failing_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="error")

    monkeypatch.setattr(subprocess, "run", _failing_run)

    uninstall_service()

    assert not provider.plist_path.exists()


def test_uninstall_service_no_warning_on_success(
    provider: LaunchdProvider,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A successful launchctl unload must not print any warning."""
    provider.plist_path.write_text("<plist/>")

    def _ok_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _ok_run)

    uninstall_service()

    captured = capsys.readouterr()
    assert "Warning" not in captured.err


def test_uninstall_service_noop_when_plist_absent(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the plist doesn't exist, uninstall_service must be a no-op returning False."""
    mock_run = MagicMock()
    monkeypatch.setattr(subprocess, "run", mock_run)

    removed = uninstall_service()

    assert removed is False
    mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# service_status reports the actual installed port
# ---------------------------------------------------------------------------


def test_service_status_reports_custom_port(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A plist installed with a non-default port surfaces in service_status."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    provider.plist_path.write_text(provider._plist("halyard", project_dir, 7777))

    # Simulate launchctl reporting the service as loaded.
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(args=a[0], returncode=0, stdout=""),
    )

    is_running, msg = service_status()
    assert is_running
    assert "http://127.0.0.1:7777/" in msg


def test_installed_port_falls_back_on_malformed_plist(
    provider: LaunchdProvider, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed plist → warning + DASHBOARD_PORT fallback, not a crash."""
    from halyard.dashboard import DASHBOARD_PORT

    provider.plist_path.write_text("<not valid xml")  # garbage

    port = provider.get_port()
    assert port == DASHBOARD_PORT
    captured = capsys.readouterr()
    assert "Warning" in captured.err


def test_installed_port_returns_default_when_plist_absent(provider: LaunchdProvider) -> None:
    """If the plist doesn't exist, get_port returns the default constant."""
    from halyard.dashboard import DASHBOARD_PORT

    assert provider.get_port() == DASHBOARD_PORT


def test_install_service_uses_trusted_halyard_resolver(
    provider: LaunchdProvider, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """LaunchAgent install must not persist an arbitrary PATH hit."""
    trusted_exe = tmp_path / ".venv" / "bin" / "halyard"
    trusted_exe.parent.mkdir(parents=True)
    trusted_exe.write_text("#!/bin/sh\n")
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    calls: list[list[str]] = []

    def _ok_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("halyard.cli_hooks._halyard_exe", lambda: str(trusted_exe))
    monkeypatch.setattr(subprocess, "run", _ok_run)

    url = install_service(project_dir, port=7777)

    assert url == "http://127.0.0.1:7777/"
    assert calls == [["launchctl", "load", "-w", str(provider.plist_path)]]
    assert f"<string>{trusted_exe}</string>" in provider.plist_path.read_text()


# ---------------------------------------------------------------------------
# v2.16 §1 — Jinja template is reachable via the package path
# ---------------------------------------------------------------------------


def test_invoice_template_resolves_via_package_path() -> None:
    """The Jinja template ships inside the installed package, not the source tree.

    Regression test for the v2.16 C1 bug: previously _template_dir() resolved
    to `Path(__file__).resolve().parents[2] / "templates"`, which only works
    when running from a source checkout. After packaging, that path is
    outside the wheel and `halyard invoice` raised TemplateNotFound.
    """
    from pathlib import Path as _Path

    import halyard
    from halyard import invoicing  # noqa: F401  (just to load the module)

    pkg_root = _Path(halyard.__file__).parent
    template = pkg_root / "templates" / "invoice.md.j2"
    assert template.exists(), f"invoice.md.j2 missing at {template}"
