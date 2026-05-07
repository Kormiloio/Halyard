"""Branch selector modal."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static


class BranchModal(ModalScreen[str | None]):
    """Select or clear a branch filter."""

    BINDINGS: ClassVar = [("escape", "clear", "clear")]

    class BranchSelected(Message):
        """Posted when a branch is selected or cleared."""

        def __init__(self, branch: str | None) -> None:
            self.branch = branch
            super().__init__()

    def __init__(self, branches: list[str], active_branch: str | None = None) -> None:
        super().__init__()
        self.branches = branches
        self.active_branch = active_branch

    def compose(self) -> ComposeResult:
        with Vertical(id="branch-modal"):
            yield Static("Branch Filter", id="branch-title")
            if not self.branches:
                yield Label("No branch tags found.")
            yield ListView(
                *[
                    ListItem(Label(_branch_label(branch, self.active_branch)), name=branch)
                    for branch in self.branches
                ],
                id="branch-list",
            )
            yield Label("Enter selects, Escape clears")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        branch = event.item.name
        self.post_message(self.BranchSelected(branch))
        self.dismiss(branch)

    def action_clear(self) -> None:
        self.post_message(self.BranchSelected(None))
        self.dismiss(None)


def _branch_label(branch: str, active_branch: str | None) -> str:
    marker = "*" if branch == active_branch else " "
    return f"{marker} {branch}"
