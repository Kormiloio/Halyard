"""Keyboard help modal."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpModal(ModalScreen[None]):
    """Show the TUI keyboard reference."""

    BINDINGS: ClassVar = [("escape", "close_help", "close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-modal"):
            yield Static("Keyboard Help", id="help-title")
            yield Static(
                "\n".join(
                    [
                        "Time window",
                        "  d    today",
                        "  w    this week",
                        "  m    this month",
                        "  a    all time",
                        "",
                        "Navigation",
                        "  ↑ ↓  select project",
                        "  Enter  drill into project",
                        "  Esc  back / clear filter",
                        "",
                        "Filters",
                        "  p    toggle project scope",
                        "  b    filter by git branch",
                        "",
                        "  ?    this help",
                        "  q    quit",
                    ]
                )
            )

    def action_close_help(self) -> None:
        self.dismiss(None)
