"""macOS LaunchAgent management for the Halyard Glass Cockpit background service."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

PLIST_LABEL = "io.kormilo.halyard"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_PATH = Path.home() / "Library" / "Logs" / "halyard-dashboard.log"


def install_service(project_dir: Path, port: int = 7432) -> str:
    """Write the LaunchAgent plist and load it. Returns the dashboard URL."""
    halyard_exe = shutil.which("halyard") or "halyard"
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_plist(halyard_exe, project_dir, port))
    subprocess.run(["launchctl", "load", "-w", str(PLIST_PATH)], check=True)
    return f"http://127.0.0.1:{port}/"


def uninstall_service() -> None:
    """Unload and remove the LaunchAgent plist."""
    if PLIST_PATH.exists():
        # L-2: capture launchctl output so we can warn on failure.
        # check=False is intentional — we still remove the plist even if unload
        # fails (e.g. service already stopped / partially loaded state).
        result = subprocess.run(
            ["launchctl", "unload", "-w", str(PLIST_PATH)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"[halyard] Warning: launchctl unload exited {result.returncode}"
                + (f": {result.stderr.strip()}" if result.stderr.strip() else ""),
                file=sys.stderr,
            )
        PLIST_PATH.unlink()


def service_status() -> tuple[bool, str]:
    """Return (is_running, message)."""
    if not PLIST_PATH.exists():
        return False, "not installed"
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, "installed but not running — run: launchctl load -w " + str(PLIST_PATH)
    from halyard.dashboard import DASHBOARD_PORT

    return True, f"http://127.0.0.1:{DASHBOARD_PORT}/"


def _plist(halyard_exe: str, project_dir: Path, port: int) -> str:
    # D-4: escape all interpolated values to prevent XML injection.
    # xml.sax.saxutils.escape() handles &, <, and > in element content.
    # The launchd plist format uses element content only (no attribute values),
    # so escape() is sufficient — quoteattr() is not needed here.
    e_exe = escape(str(halyard_exe))
    e_project_dir = escape(str(project_dir))
    e_port = escape(str(port))
    e_log_path = escape(str(LOG_PATH))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
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
