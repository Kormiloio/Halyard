"""Tests for the v4.0 Hub service providers (systemd, launchd)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from halyard.service_providers.launchd import LaunchdProvider
from halyard.service_providers.systemd import SystemdProvider


@pytest.fixture
def mock_subprocess():
    with patch("subprocess.run") as mock:
        mock.return_value = MagicMock(returncode=0, stdout="active\n")
        yield mock


def test_systemd_provider_install(mock_subprocess, tmp_path):
    # Mock home directory for systemd unit file
    with patch("pathlib.Path.home", return_value=tmp_path):
        provider = SystemdProvider("halyard-test")
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        url = provider.install(project_dir, port=8000)

        assert url == "http://127.0.0.1:8000/"
        assert provider.unit_path.exists()
        content = provider.unit_path.read_text(encoding="utf-8")
        assert "ExecStart=" in content
        assert "--port 8000" in content

        # Verify systemctl calls
        assert mock_subprocess.call_count >= 2
        args = [call.args[0] for call in mock_subprocess.call_args_list]
        assert ["systemctl", "--user", "daemon-reload"] in args
        assert ["systemctl", "--user", "enable", "--now", "halyard-test"] in args


def test_launchd_provider_install(mock_subprocess, tmp_path):
    with patch("pathlib.Path.home", return_value=tmp_path):
        provider = LaunchdProvider("halyard-test")
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        url = provider.install(project_dir, port=9000)

        assert url == "http://127.0.0.1:9000/"
        assert provider.plist_path.exists()
        content = provider.plist_path.read_text(encoding="utf-8")
        assert "<string>--port</string>" in content
        assert "<string>9000</string>" in content

        # Verify launchctl calls
        mock_subprocess.assert_called_with(
            ["launchctl", "load", "-w", str(provider.plist_path)], check=True
        )


def test_systemd_status_parsing(mock_subprocess, tmp_path):
    with patch("pathlib.Path.home", return_value=tmp_path):
        provider = SystemdProvider("halyard-test")
        provider.unit_path.parent.mkdir(parents=True)
        provider.unit_path.write_text(
            "ExecStart=/bin/halyard dashboard --port 1234", encoding="utf-8"
        )

        assert provider.get_port() == 1234

        mock_subprocess.return_value.stdout = "active\n"
        is_running, msg = provider.status()
        assert is_running is True
        assert "1234" in msg


def test_launchd_status_parsing(mock_subprocess, tmp_path):
    with patch("pathlib.Path.home", return_value=tmp_path):
        provider = LaunchdProvider("halyard-test")
        provider.plist_path.parent.mkdir(parents=True)

        import plistlib

        data = {"ProgramArguments": ["halyard", "dashboard", "--port", "5678"]}
        with provider.plist_path.open("wb") as fh:
            plistlib.dump(data, fh)

        assert provider.get_port() == 5678

        mock_subprocess.return_value.returncode = 0
        is_running, msg = provider.status()
        assert is_running is True
        assert "5678" in msg
