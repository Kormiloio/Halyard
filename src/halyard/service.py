"""macOS LaunchAgent management for the Halyard background dashboard service (The Bridge)."""

from __future__ import annotations

import os
import plistlib
import secrets
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from xml.sax.saxutils import escape

PLIST_LABEL = "io.kormilo.halyard"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
LOG_PATH = Path.home() / "Library" / "Logs" / "halyard-dashboard.log"


# ---------------------------------------------------------------------------
# C2: Dashboard token helpers
# ---------------------------------------------------------------------------


def _token_path() -> Path:
    """Return the path to the per-install dashboard token file."""
    return Path.home() / ".halyard" / "dashboard.token"


def _load_or_create_token() -> str:
    """Return the dashboard auth token, creating it if absent.

    The token is a 32-byte (64 hex char) secret stored at mode 0600.
    It is set as a cookie on every GET / response and validated on every
    POST.  Cross-origin pages cannot read the cookie (HttpOnly + SameSite=Strict)
    and cannot read the file, so they cannot forge a valid request.
    """
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        token = path.read_text().strip()
        if len(token) == 64 and all(c in "0123456789abcdef" for c in token):
            # A token written before the 0600 logic (or with loosened perms)
            # would otherwise stay world-readable for its whole lifetime.
            with suppress(OSError):
                os.chmod(path, 0o600)
            return token
    # Generate fresh token and write with 0600 permissions
    token = secrets.token_hex(32)
    # Write atomically via a temp file, then chmod before rename
    tmp = path.with_suffix(".token.tmp")
    tmp.write_text(token)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return token


def install_service(project_dir: Path, port: int = 7432) -> str:
    """Write the LaunchAgent plist and load it. Returns the dashboard URL."""
    from halyard.cli_hooks import _halyard_exe

    halyard_exe = _halyard_exe()
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


def _installed_port() -> int:
    """Read the port written into the installed plist's ProgramArguments.

    Returns the parsed port on success.  On any failure (missing file,
    malformed XML, --port flag absent, non-integer value) falls back to the
    DASHBOARD_PORT constant and emits a one-line warning so the user knows
    the reported URL may not match a previously-customized install.
    """
    from halyard.dashboard import DASHBOARD_PORT

    if not PLIST_PATH.exists():
        return DASHBOARD_PORT
    try:
        with PLIST_PATH.open("rb") as fh:
            data = plistlib.load(fh)
        if not isinstance(data, dict):
            return DASHBOARD_PORT
        args = data.get("ProgramArguments") or []
        for i, token in enumerate(args):
            if token == "--port" and i + 1 < len(args):
                return int(args[i + 1])
    except (OSError, plistlib.InvalidFileException, ValueError) as exc:
        print(
            f"[halyard] Warning: could not parse port from {PLIST_PATH} "
            f"({type(exc).__name__}); reporting default {DASHBOARD_PORT}.",
            file=sys.stderr,
        )
    return DASHBOARD_PORT


def service_status() -> tuple[bool, str]:
    """Return (is_running, message).

    The message includes the dashboard URL and the location of the per-install
    auth token.  If the token is ever compromised, run:
        halyard service uninstall && halyard service install
    which regenerates a fresh token.
    """
    if not PLIST_PATH.exists():
        return False, "not installed"
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, "installed but not running — run: launchctl load -w " + str(PLIST_PATH)
    port = _installed_port()
    token_note = f" | token: {_token_path()}"
    return True, f"http://127.0.0.1:{port}/{token_note}"


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
