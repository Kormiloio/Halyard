"""Optional Textual TUI for Halyard."""

from __future__ import annotations

_INSTALL_MESSAGE = (
    "Textual is required for the interactive dashboard. Install it with:\n"
    "  pip install halyard[tui]"
)

__all__ = ["HalyardApp"]


def __getattr__(name: str) -> object:
    if name != "HalyardApp":
        raise AttributeError(name)
    try:
        from halyard.tui.app import HalyardApp
    except ImportError as exc:
        if exc.name and (exc.name == "textual" or exc.name.startswith("textual.")):
            raise ImportError(_INSTALL_MESSAGE) from exc
        raise
    return HalyardApp
