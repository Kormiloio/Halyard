"""Linux systemd service provider."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from halyard.service_manager import ServiceProvider


class SystemdProvider(ServiceProvider):
    def __init__(self, label: str):
        super().__init__(label)
        self.unit_path = Path.home() / ".config" / "systemd" / "user" / f"{label}.service"

    def install(self, project_dir: Path, port: int) -> str:
        from halyard.cli_hooks import _halyard_exe

        halyard_exe = _halyard_exe()
        self.unit_path.parent.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text(self._unit_file(halyard_exe, project_dir, port), encoding="utf-8")
        # v5.18/B23: the unit's ExecStart exposes the halyard exe path,
        # project_dir, and port the user auto-runs at login. write_text honours
        # the umask (commonly world-readable 0o644); restrict to owner-only.
        os.chmod(self.unit_path, 0o600)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", self.label], check=True)
        return f"http://127.0.0.1:{port}/"

    def uninstall(self) -> bool:
        if not self.unit_path.exists():
            return False
        subprocess.run(["systemctl", "--user", "disable", "--now", self.label], check=False)
        self.unit_path.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        return True

    def status(self) -> tuple[bool, str]:
        if not self.unit_path.exists():
            return False, "not installed"
        result = subprocess.run(
            ["systemctl", "--user", "is-active", self.label],
            capture_output=True,
            text=True,
        )
        is_running = result.stdout.strip() == "active"
        port = self.get_port()
        from halyard.service import _token_path

        token_note = f" | token: {_token_path()}"
        return is_running, f"http://127.0.0.1:{port}/{token_note}"

    def get_port(self) -> int:
        from halyard.dashboard import DASHBOARD_PORT

        if not self.unit_path.exists():
            return DASHBOARD_PORT
        try:
            content = self.unit_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if "ExecStart=" in line and "--port" in line:
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p == "--port" and i + 1 < len(parts):
                            return int(parts[i + 1])
        except (OSError, ValueError):
            pass
        return DASHBOARD_PORT

    def _unit_file(self, halyard_exe: str, project_dir: Path, port: int) -> str:
        exe = _sd_quote(str(halyard_exe))
        proj = _sd_quote(str(project_dir))
        return f"""[Unit]
Description=Halyard Dashboard Service
After=network.target

[Service]
ExecStart={exe} dashboard --project-dir {proj} --port {port}
Restart=always

[Install]
WantedBy=default.target
"""


def _sd_quote(value: str) -> str:
    """Double-quote a value for a systemd ExecStart argument.

    systemd splits ExecStart on whitespace unless arguments are quoted, and
    treats backslash/quote/newline specially. Without this, a project path
    containing a space splits into multiple argv entries (wrong --project-dir),
    and a newline could inject additional unit directives.
    """
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    )
    return f'"{escaped}"'
