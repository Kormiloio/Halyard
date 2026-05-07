"""Session feed widget."""

from __future__ import annotations

from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.tui.formatters import cost_str, duration_str, tool_icon, truncate


class SessionFeed(Static):
    """Render the current session list."""

    session_count = 0
    selected_index = 0

    def render_sessions(self, sessions: list[AiSession], selected_index: int = 0) -> None:
        self.session_count = len(sessions)
        self.selected_index = selected_index
        if not sessions:
            self.update("No sessions captured yet.")
            return

        lines = ["Session Feed", ""]
        for index, session in enumerate(sessions[:50]):
            tokens = session.input_tokens + session.output_tokens
            project = session.project or "(unattributed)"
            marker = ">" if index == selected_index else " "
            line = (
                f"{marker} {tool_icon(session.tool)} "
                f"{truncate(session.model, 20):20} "
                f"{truncate(project, 22):22} "
                f"{duration_str(session.end - session.start):>7} "
                f"{tokens:>8} tok "
                f"{cost_str(session.cost_usd):>9}"
            )
            lines.append(line)
        self.update("\n".join(lines))
