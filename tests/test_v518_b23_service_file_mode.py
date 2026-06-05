"""Regression tests for B23 — world-readable service unit files (v5.18).

The launchd plist and the systemd user unit embed the halyard executable
path, the project_dir, and the dashboard port that the victim auto-runs at
login. Before B23 they were written via ``write_text`` under the process
umask (commonly 0o644), exposing those details to every local user. The fix
chmods each unit to 0o600 immediately after writing.

These tests assert (a) the malicious exposure is closed — the on-disk file is
owner-only — and (b) a benign install still produces a working, readable unit
for the owner (guard against over-restriction).
"""

from __future__ import annotations

import stat
import sys
from unittest.mock import MagicMock, patch

import pytest

from halyard.service_providers.launchd import LaunchdProvider
from halyard.service_providers.systemd import SystemdProvider

# os.chmod mode bits are only POSIX-meaningful; on Windows os.chmod merely
# toggles the read-only attribute, so the 0o600 group/other assertions do not
# apply there. The source fix itself stays cross-platform (unconditional
# os.chmod, matching the existing cross-platform style).
pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX file-mode bits are not meaningful on Windows"
)


@pytest.fixture
def mock_subprocess():
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(returncode=0, stdout="active\n")
        yield mock


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_systemd_unit_is_owner_only(mock_subprocess, tmp_path):
    """Malicious-exposure guard: the systemd unit must not be group/world readable."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        provider = SystemdProvider("halyard-test")
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        provider.install(project_dir, port=8000)

        mode = _mode(provider.unit_path)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
        # No access for group or other — the secret path/port stays private.
        assert not (mode & (stat.S_IRWXG | stat.S_IRWXO))


def test_launchd_plist_is_owner_only(mock_subprocess, tmp_path):
    """Malicious-exposure guard: the launchd plist must not be group/world readable."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        provider = LaunchdProvider("halyard-test")
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        provider.install(project_dir, port=9000)

        mode = _mode(provider.plist_path)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
        assert not (mode & (stat.S_IRWXG | stat.S_IRWXO))


def test_systemd_owner_can_still_read_and_install_works(mock_subprocess, tmp_path):
    """Over-restriction guard: a benign install still yields a working, owner-readable unit."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        provider = SystemdProvider("halyard-test")
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        url = provider.install(project_dir, port=8000)

        assert url == "http://127.0.0.1:8000/"
        assert _mode(provider.unit_path) & stat.S_IRUSR  # owner can read
        # Content intact and parsable by the owner — port round-trips.
        content = provider.unit_path.read_text(encoding="utf-8")
        assert "--port 8000" in content
        assert provider.get_port() == 8000


def test_launchd_owner_can_still_read_and_install_works(mock_subprocess, tmp_path):
    """Over-restriction guard: a benign install still yields a working, owner-readable plist."""
    with patch("pathlib.Path.home", return_value=tmp_path):
        provider = LaunchdProvider("halyard-test")
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        url = provider.install(project_dir, port=9000)

        assert url == "http://127.0.0.1:9000/"
        assert _mode(provider.plist_path) & stat.S_IRUSR  # owner can read
        content = provider.plist_path.read_text(encoding="utf-8")
        assert "<string>9000</string>" in content
        assert provider.get_port() == 9000
