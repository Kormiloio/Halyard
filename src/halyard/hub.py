"""Hub — global fallback log directory for cross-project session capture.

When a hook fires outside any directory that contains a halyard.toml, sessions
would normally be silently dropped.  The hub is a single Halyard project
directory that acts as a catch-all: all tools write there when no local project
matches.

The hub path is stored as a single line in ~/.halyard/hub.
Set it with ``halyard init --hub`` or ``halyard hub set <path>``.
"""

from __future__ import annotations

from pathlib import Path

_HUB_POINTER: Path | None = None


def _hub_pointer() -> Path:
    if _HUB_POINTER is not None:
        return _HUB_POINTER
    return Path.home() / ".halyard" / "hub"


def find_hub() -> Path | None:
    """Return the hub project directory, or None if not configured."""
    pointer = _hub_pointer()
    if not pointer.exists():
        return None
    try:
        path = Path(pointer.read_text().strip())
    except OSError:
        return None
    return path if path.is_dir() else None


def set_hub(path: Path) -> None:
    """Designate path as the hub directory."""
    pointer = _hub_pointer()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(path.resolve()) + "\n")


def clear_hub() -> None:
    _hub_pointer().unlink(missing_ok=True)
