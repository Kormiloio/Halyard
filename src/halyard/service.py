"""Service management for the Halyard background dashboard service (The Bridge)."""

from __future__ import annotations

import os
import secrets
from contextlib import suppress
from pathlib import Path

from halyard.service_manager import get_provider

PLIST_LABEL = "io.kormilo.halyard"


def _token_path() -> Path:
    """Return the path to the per-install dashboard token file."""
    return Path.home() / ".halyard" / "dashboard.token"


def _load_or_create_token() -> str:
    """Return the dashboard auth token, creating it if absent."""
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) == 64 and all(c in "0123456789abcdef" for c in token):
            with suppress(OSError):
                os.chmod(path, 0o600)
            return token
    token = secrets.token_hex(32)
    tmp = path.with_suffix(".token.tmp")
    tmp.write_text(token, encoding="utf-8")
    os.chmod(tmp, 0o600)
    from halyard.ai_log import atomic_replace

    atomic_replace(tmp, path)
    return token


def install_service(project_dir: Path, port: int = 7432) -> str:
    """Install and start the service via the appropriate provider."""
    provider = get_provider(PLIST_LABEL)
    return provider.install(project_dir, port)


def uninstall_service() -> bool:
    """Unload and remove the service via the appropriate provider.

    Returns True if a service was actually removed, False if none was installed.
    """
    provider = get_provider(PLIST_LABEL)
    return provider.uninstall()


def service_status() -> tuple[bool, str]:
    """Return (is_running, message) via the appropriate provider."""
    provider = get_provider(PLIST_LABEL)
    return provider.status()
