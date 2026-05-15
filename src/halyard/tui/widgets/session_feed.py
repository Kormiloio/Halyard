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
            meta_badge = _metadata_badge(session)
            outcome_badge = _outcome_badge(session)
            line = (
                f"{marker} {tool_icon(session.tool)} "
                f"{truncate(session.model, 20):20} "
                f"{truncate(project, 22):22} "
                f"{duration_str(session.end - session.start):>7} "
                f"{tokens:>8} tok "
                f"{cost_str(session.cost_usd):>9}"
                f"{err_badge}{meta_badge}{branch_badge}{outcome_badge}"
            )
            lines.append(line)
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)


_OUTCOME_GLYPH = {
    "merged": "✓",
    "open": "•",
    "closed": "✗",
    "none": "—",
}


def _outcome_badge(session: AiSession) -> str:
    """Render the v3.0 outcome state as a compact glyph + PR ref.

    Examples: " ✓ owner/repo#42" (merged), " • #42" (open), " ✗ closed" (closed).
    Returns "" when no outcome is attached.
    """
    if not session.pr_state and not session.pr_ref:
        return ""
    glyph = _OUTCOME_GLYPH.get(session.pr_state or "", "?")
    if session.pr_ref:
        return f" {glyph} {session.pr_ref}"
    return f" {glyph} {session.pr_state or '?'}"


def _metadata_badge(session: AiSession) -> str:
    bits: list[str] = []
    if session.interaction_count is not None:
        bits.append(f"{session.interaction_count}i")
    elif session.interaction_data_available is False:
        bits.append("i n/a")
    if session.files_touched_count is not None:
        bits.append(f"{session.files_touched_count}f")
    if session.test_status:
        bits.append(f"test:{session.test_status}")
    if not bits:
        return ""
    return " " + " ".join(bits)
