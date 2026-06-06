"""Service management for the Halyard background dashboard service (The Bridge)."""

from __future__ import annotations

import errno
import os
import secrets
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

from halyard.service_manager import get_provider

PLIST_LABEL = "io.kormilo.halyard"

# Windows lacks O_NOFOLLOW; 0 is a no-op flag bit there (symlink attacks on
# the token path are a POSIX-shared-host concern, mitigated by the 0o700 dir).
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _token_path() -> Path:
    """Return the path to the per-install dashboard token file."""
    return Path.home() / ".halyard" / "dashboard.token"


def _is_valid_token(token: str) -> bool:
    return len(token) == 64 and all(c in "0123456789abcdef" for c in token)


def _ensure_halyard_dir() -> Path:
    """Create ``~/.halyard`` and tighten it to owner-only (0o700).

    v5.19/B2: a world-traversable parent enables a symlink pre-placement
    attack on the token path; 0o700 keeps the directory private to us.
    """
    d = _token_path().parent
    d.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):  # best-effort; chmod is a near no-op on Windows
        d.chmod(0o700)
    return d


def _read_token_if_ours(path: Path) -> str | None:
    """Return a valid token from ``path`` iff it is a regular file owned by us
    and not group/other-accessible — else None so the caller recreates it.

    v5.19/B2: the previous code trusted ANY pre-existing 64-hex file, letting
    an attacker who can plant the file control the auth secret. We adopt a
    token only when ``st_uid == getuid()`` and tighten loose perms fail-closed
    (the corrective chmod is NOT suppressed).
    """
    try:
        st = path.lstat()  # lstat: never follow a planted symlink
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None  # symlink / dir / fifo squatting on the path — don't trust
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        return None  # planted by another user — don't trust
    if st.st_mode & 0o077:
        os.chmod(path, 0o600)  # group/other can see it — tighten, fail closed
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token if _is_valid_token(token) else None


def _force_replace_token(path: Path, token: str) -> str:
    """Atomically install ``token`` at ``path`` over an untrusted occupant
    (e.g. a planted symlink/file). Temp is created 0o600 by mkstemp."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".dashboard.token.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token)
        os.replace(tmp, path)  # atomic
    except OSError:
        with suppress(OSError):
            os.unlink(tmp)
        raise
    return token


def _load_or_create_token() -> str:
    """Return the dashboard auth token, creating it securely if absent.

    v5.19/B2: created with ``O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW`` at mode
    0o600 — the secret is never world-readable for an instant (mode is set at
    creation, not after), the path cannot be a pre-placed symlink
    (``O_NOFOLLOW``), and concurrent first-run callers cannot diverge
    (``O_EXCL``: exactly one process creates it; the losers re-read and return
    the winner's token, so no client is left holding a token the file no
    longer matches).
    """
    path = _token_path()
    _ensure_halyard_dir()

    existing = _read_token_if_ours(path)
    if existing is not None:
        return existing

    token = secrets.token_hex(32)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        if exc.errno not in (errno.EEXIST, errno.ELOOP):
            raise
        # Lost the race, or an untrusted file occupies the path.
        existing = _read_token_if_ours(path)
        if existing is not None:
            return existing  # a sibling process created a valid token — use it
        return _force_replace_token(path, token)  # untrusted occupant — replace
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
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
