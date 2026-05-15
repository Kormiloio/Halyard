"""System health detail modal (TUI parity with the web v2.43 popup)."""

from __future__ import annotations

from typing import ClassVar

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from halyard.reports import HealthCheck

_DOT = {"error": "✖", "warning": "⚠"}


class HealthModal(ModalScreen[None]):
    """List failing health checks and point to `halyard doctor`."""

    BINDINGS: ClassVar = [
        ("escape", "close_health", "close"),
        ("h", "close_health", "close"),
    ]

    def __init__(self, checks: list[HealthCheck]) -> None:
        super().__init__()
        self._failing = [c for c in checks if c.status in ("warning", "error")]

    def compose(self) -> ComposeResult:
        with Vertical(id="health-modal"):
            yield Static("System Health", id="health-title")
            if not self._failing:
                yield Static("✓ All systems healthy.")
                return
            lines = []
            for c in self._failing:
                dot = _DOT.get(c.status, "•")
                # escape: a crafted project/detail must not inject markup.
                lines.append(f"{dot}  {escape(c.label)} — {escape(c.detail)}")
            yield Static("\n".join(lines))
            yield Static(
                "\nRun `halyard doctor` for full diagnostics and fixes.",
                id="health-doctor-hint",
            )

    def action_close_health(self) -> None:
        self.dismiss(None)
