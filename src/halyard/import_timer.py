"""macOS LaunchAgent for the scheduled importer (keeps importer-based tools fresh).

Codex, Copilot, and Gemini are import-based collectors: their sessions only
reach the ledger when an importer runs. Without a schedule they silently lag
between manual imports. This installs a LaunchAgent that runs
``halyard import-all`` on an interval — idempotent, so already-imported
sessions are skipped.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

PLIST_LABEL = "io.kormilo.halyard.import"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_PATH = Path.home() / ".halyard" / "import-timer.log"

# Default cadence: every 30 minutes. Importers are cheap and idempotent.
DEFAULT_INTERVAL_SECONDS = 1800


def install_import_timer(interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> str:
    """Write the LaunchAgent plist and load it. Returns the plist path."""
    from halyard.cli_hooks import _halyard_exe

    halyard_exe = _halyard_exe()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_plist(halyard_exe, interval_seconds))
    # Reload idempotently: unload first (ignore failure), then load.
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True, text=True)
    subprocess.run(["launchctl", "load", "-w", str(PLIST_PATH)], check=True)
    return str(PLIST_PATH)


def uninstall_import_timer() -> None:
    """Unload and remove the LaunchAgent plist."""
    if PLIST_PATH.exists():
        result = subprocess.run(
            ["launchctl", "unload", "-w", str(PLIST_PATH)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and result.stderr.strip():
            print(
                f"[halyard] Warning: launchctl unload exited {result.returncode}: "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
        PLIST_PATH.unlink()


def import_timer_status() -> tuple[bool, str]:
    """Return (installed, message)."""
    if not PLIST_PATH.exists():
        return False, "not installed"
    result = subprocess.run(["launchctl", "list", PLIST_LABEL], capture_output=True, text=True)
    running = result.returncode == 0
    return running, f"installed at {PLIST_PATH} (log: {LOG_PATH})"


def _plist(halyard_exe: str, interval_seconds: int) -> str:
    e_exe = escape(str(halyard_exe))
    e_log = escape(str(LOG_PATH))
    e_interval = escape(str(int(interval_seconds)))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{e_exe}</string>
        <string>import-all</string>
    </array>
    <key>StartInterval</key>
    <integer>{e_interval}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{e_log}</string>
    <key>StandardErrorPath</key>
    <string>{e_log}</string>
</dict>
</plist>
"""
