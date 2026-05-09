"""Session feed widget."""

from __future__ import annotations

from datetime import datetime

from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.tui.formatters import cost_str, duration_str, tool_icon, truncate

_NEW_ARRIVAL_SECONDS = 30


class SessionFeed(Static):
    """Render the current session list."""

    session_count = 0
    selected_index = 0
    last_rendered_text = ""

    def render_sessions(self, sessions: list[AiSession], selected_index: int = 0) -> None:
        self.session_count = len(sessions)
        self.selected_index = selected_index
        if not sessions:
            self.last_rendered_text = "No sessions captured yet."
            self.update(self.last_rendered_text)
            return

        now = datetime.now()
        lines = ["⚓  Ship's Log", ""]
        for index, session in enumerate(sessions[:50]):
            tokens = session.input_tokens + session.output_tokens
            project = session.project or "(unattributed)"
            is_new = (now - session.end).total_seconds() < _NEW_ARRIVAL_SECONDS
            marker = "▶" if index == selected_index else ("+" if is_new else " ")
            err_badge = f" ⚠{session.tool_errors}e" if session.tool_errors else ""
            branch_badge = f" [{session.branch}]" if session.branch else ""
            line = (
                f"{marker} {tool_icon(session.tool)} "
                f"{truncate(session.model, 20):20} "
                f"{truncate(project, 22):22} "
                f"{duration_str(session.end - session.start):>7} "
                f"{tokens:>8} tok "
                f"{cost_str(session.cost_usd):>9}"
                f"{err_badge}{branch_badge}"
            )
            lines.append(line)
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)
