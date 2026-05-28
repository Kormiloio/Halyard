"""macOS LaunchAgent (launchd) service provider."""

from __future__ import annotations

import plistlib
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from halyard.service_manager import ServiceProvider


class LaunchdProvider(ServiceProvider):
    def __init__(self, label: str):
        super().__init__(label)
        self.plist_path = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
        self.log_path = Path.home() / "Library" / "Logs" / "halyard-dashboard.log"

    def install(self, project_dir: Path, port: int) -> str:
        from halyard.cli_hooks import _halyard_exe

        halyard_exe = _halyard_exe()
        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        self.plist_path.write_text(self._plist(halyard_exe, project_dir, port), encoding="utf-8")
        subprocess.run(["launchctl", "load", "-w", str(self.plist_path)], check=True)
        return f"http://127.0.0.1:{port}/"

    def uninstall(self) -> bool:
        if not self.plist_path.exists():
            return False
        result = subprocess.run(
            ["launchctl", "unload", "-w", str(self.plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(
                f"[halyard] Warning: launchctl unload exited {result.returncode}: "
                f"{(result.stderr or '').strip()}",
                file=sys.stderr,
            )
        # Remove the plist even when unload failed (e.g. already stopped) so the
        # service does not reload at next login; the warning above flags the case.
        self.plist_path.unlink()
        return True

    def status(self) -> tuple[bool, str]:
        if not self.plist_path.exists():
            return False, "not installed"
        result = subprocess.run(
            ["launchctl", "list", self.label],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return (
                False,
                f"installed but not running — run: launchctl load -w {self.plist_path}",
            )
        port = self.get_port()
        from halyard.service import _token_path

        token_note = f" | token: {_token_path()}"
        return True, f"http://127.0.0.1:{port}/{token_note}"

    def get_port(self) -> int:
        from halyard.dashboard import DASHBOARD_PORT

        if not self.plist_path.exists():
            return DASHBOARD_PORT
        try:
            with self.plist_path.open("rb") as fh:
                data = plistlib.load(fh)
            if not isinstance(data, dict):
                raise ValueError("plist root is not a dictionary")
            args = data.get("ProgramArguments") or []
            for i, token in enumerate(args):
                if token == "--port" and i + 1 < len(args):
                    return int(args[i + 1])
        except (OSError, plistlib.InvalidFileException, ValueError) as exc:
            print(
                f"[halyard] Warning: could not read port from {self.plist_path}: {exc}",
                file=sys.stderr,
            )
        return DASHBOARD_PORT

    def _plist(self, halyard_exe: str, project_dir: Path, port: int) -> str:
        e_exe = escape(str(halyard_exe))
        e_project_dir = escape(str(project_dir))
        e_port = escape(str(port))
        e_log_path = escape(str(self.log_path))
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self.label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{e_exe}</string>
        <string>dashboard</string>
        <string>--project-dir</string>
        <string>{e_project_dir}</string>
        <string>--port</string>
        <string>{e_port}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{e_log_path}</string>
    <key>StandardErrorPath</key>
    <string>{e_log_path}</string>
</dict>
</plist>
"""
