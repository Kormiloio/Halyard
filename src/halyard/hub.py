"""Hub — global fallback log directory for cross-project session capture.

When a hook fires outside any directory that contains a halyard.toml, sessions
would normally be silently dropped.  The hub is a single Halyard project
directory that acts as a catch-all: all tools write there when no local project
matches.

The hub path is stored as a single line in ~/.halyard/hub.
Set it with ``halyard init --hub`` or ``halyard hub set <path>``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from halyard.ai_log import AI_LOG_FILENAME


@dataclass(frozen=True)
class HubStatus:
    path: Path | None
    session_count: int = 0


_HUB_POINTER: Path | None = None


def _hub_pointer() -> Path:
    if _HUB_POINTER is not None:
        return _HUB_POINTER
    return Path.home() / ".halyard" / "hub"


def find_hub() -> Path | None:
    """Return the hub project directory, or None if not configured.

    Goes through :func:`halyard.state_integrity.read_global_trusted_state`
    so an existing sidecar on disk is honored even when the resolved
    mode is ``off`` — otherwise a tampered ``~/.halyard/hub`` pointer
    would be silently accepted in the default runtime. On
    IntegrityError, returns None — the rest of Halyard will fall back
    to project-dir discovery.
    """
    from halyard.state_integrity import IntegrityError, read_global_trusted_state

    pointer = _hub_pointer()
    try:
        content = read_global_trusted_state(pointer)
    except (IntegrityError, OSError):
        return None
    if content is None:
        return None
    path = Path(content.strip())
    return path if path.is_dir() else None


def configured_hub_path() -> Path | None:
    """Return the hub path as configured, whether or not it exists.

    :func:`find_hub` deliberately collapses "never configured" and
    "configured but the directory is gone" into ``None`` — its ~40
    call sites only ever ask "is there a hub I can write to right
    now?", and both answers are the same for them. That is the wrong
    contract for the doctor, which has to explain *why* capture is
    failing: a pointer at a relocated directory silently diverts every
    ambient session to ``~/.halyard/unattributed.log`` while reporting
    itself as "no hub configured".

    Returns None only when no pointer exists (or it cannot be read).
    """
    from halyard.state_integrity import IntegrityError, read_global_trusted_state

    try:
        content = read_global_trusted_state(_hub_pointer())
    except (IntegrityError, OSError):
        return None
    if content is None:
        return None
    stripped = content.strip()
    return Path(stripped) if stripped else None


def set_hub(path: Path) -> None:
    """Designate path as the hub directory."""
    from halyard.state_integrity import current_mode, write_trusted_state

    if not (path / "halyard.toml").exists():
        raise ValueError(f"Directory {path} has no halyard.toml")
    pointer = _hub_pointer()
    write_trusted_state(pointer, str(path.resolve()) + "\n", mode=current_mode(path))


def clear_hub() -> None:
    pointer = _hub_pointer()
    pointer.unlink(missing_ok=True)
    # Remove sidecar too so a future hash-mode read does not see orphan state.
    pointer.with_suffix(pointer.suffix + ".sha256").unlink(missing_ok=True)
    pointer.with_suffix(pointer.suffix + ".hmac").unlink(missing_ok=True)


def get_hub_status() -> HubStatus:
    """Return a summary of the current hub state."""
    hub_dir = find_hub()
    if hub_dir is None:
        return HubStatus(path=None)

    log_path = hub_dir / AI_LOG_FILENAME
    lines = (
        sum(1 for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.startswith("s "))
        if log_path.exists()
        else 0
    )
    return HubStatus(path=hub_dir, session_count=lines)
