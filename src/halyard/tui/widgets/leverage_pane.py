"""Leverage widget — "is the AI spend producing shipped work?".

Same buckets as the web dashboard Leverage panel; both call
`leverage.summarize`, so the surfaces cannot diverge.
"""

from __future__ import annotations

from datetime import datetime

from rich.markup import escape
from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.leverage import (
    humanize_seconds,
    render_mcp_phrase,
    render_rejection_phrase,
    summarize,
    summarize_mcp,
    summarize_struggle,
)


class LeveragePane(Static):
    """Render the shipped-rate rollup for the active TUI filter."""

    last_rendered_text = ""

    def render_sessions(self, sessions: list[AiSession], now: datetime | None = None) -> None:
        when = now or datetime.now()
        s = summarize(sessions, when)
        if s.total == 0:
            self.last_rendered_text = "⚑ Leverage\n\nNo sessions in the last 30 days."
            self.update(self.last_rendered_text)
            return

        lines = [
            "⚑ Leverage (30d)",
            "",
            f"Shipped {s.pct}%  ({s.merged} of {s.total} in merged PRs)",
        ]
        # v3.1: friction line, parity with web; only when data exists.
        friction = []
        if s.median_time_to_merge_s is not None:
            friction.append(f"~{humanize_seconds(s.median_time_to_merge_s)} to merge")
        if s.median_review_comments is not None:
            friction.append(f"~{s.median_review_comments} review comments")
        if friction:
            lines.append(" · ".join(friction))
        # v3.2: struggle line, parity with web; same shared summary so
        # the numbers cannot diverge. Only when tool-call data exists.
        st = summarize_struggle(sessions, when)
        if st.tool_error_total is not None:
            seg = f"{st.tool_error_total} tool errors"
            if st.tool_error_rate is not None:
                seg += f" ({st.tool_error_rate:.0%})"
            seg += " · " + render_rejection_phrase(st)
            lines.append(seg)
        # v3.4: MCP capability line, parity with web (shared summary).
        mcp = summarize_mcp(sessions, when)
        if mcp is not None:
            # v5.16/B19: escape before the phrase reaches Static.update ->
            # Text.from_markup (defense-in-depth; summarize_mcp already
            # allowlist-filters the names). Matches the escaping discipline
            # used by the other panes (session_feed, project_pane, ...).
            lines.append(escape(render_mcp_phrase(mcp)))
        lines += [
            "",
            f"Merged   {s.merged:>3}",
            f"Open     {s.open_:>3}",
            f"Closed   {s.closed:>3}",
            f"No PR    {s.none:>3}",
            f"Unsynced {s.unsynced:>3}",
        ]
        if s.unsynced:
            lines.append("")
            lines.append("Run halyard outcome sync to resolve unsynced.")
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)
