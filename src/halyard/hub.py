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

_HUB_POINTER = Path.home() / ".halyard" / "hub"


def find_hub() -> Path | None:
    """Return the hub project directory, or None if not configured."""
    if not _HUB_POINTER.exists():
        return None
    try:
        path = Path(_HUB_POINTER.read_text().strip())
    except OSError:
        return None
    return path if path.is_dir() else None


def set_hub(path: Path) -> None:
    """Designate path as the hub directory."""
    _HUB_POINTER.parent.mkdir(parents=True, exist_ok=True)
    _HUB_POINTER.write_text(str(path.resolve()) + "\n")


def clear_hub() -> None:
    _HUB_POINTER.unlink(missing_ok=True)
