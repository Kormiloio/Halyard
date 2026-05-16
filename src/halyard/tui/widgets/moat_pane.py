"""Moat widget — TUI mirror of the web dashboard moat story.

Information parity, not pixels: cost-by-client, attribution-confidence
mix, leakage rows with the exact one-command fix, and per-project
billable evidence. All numbers come from the shared `moat` builders so
the TUI and web can never disagree. Pure read; every model/remote/
client string is Rich-markup-escaped (v2.38 invariant).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from rich.markup import escape
from textual.widgets import Static

from halyard.ai_log import AiSession, unattributed_log_path
from halyard.attribution import format_attribution_mix
from halyard.moat import cost_by_client, leakage, project_evidence
from halyard.tui.formatters import cost_str, truncate


def _bar(value: float, peak: float, width: int = 12) -> str:
    if peak <= 0:
        return "-"
    filled = max(1, round((value / peak) * width))
    return "#" * min(width, filled)


class MoatPane(Static):
    """Render the moat story for the active TUI filter."""

    last_rendered_text = ""

    def render_sessions(
        self,
        sessions: list[AiSession],
        project_dir: Path | None = None,
        now: datetime | None = None,
    ) -> None:
        if not sessions:
            self.last_rendered_text = "⚓ Moat\n\nNo sessions in view."
            self.update(self.last_rendered_text)
            return

        lines: list[str] = ["⚓ Moat", ""]

        # --- Cost by client (totals across the view) ---------------------
        totals: dict[str, float] = defaultdict(float)
        for pt in cost_by_client(sessions):
            totals[pt.project] += pt.cost_usd
        lines.append("Cost by client")
        if totals:
            peak = max(totals.values())
            for project, cost in sorted(totals.items(), key=lambda kv: -kv[1])[:6]:
                label = escape(truncate(project, 22))
                lines.append(f"{label:22} {cost_str(cost):>9} {_bar(cost, peak)}")
        else:
            lines.append("  (none)")

        # --- Attribution confidence mix ----------------------------------
        lines.extend(["", "Attribution", f"  {escape(format_attribution_mix(sessions))}"])

        # --- Per-project billable evidence -------------------------------
        lines.extend(["", "Billable evidence"])
        for ev in project_evidence(sessions, project_dir)[:6]:
            human = "--" if ev.human_minutes is None else f"{ev.human_minutes / 60:.1f}h"
            label = escape(truncate(ev.project, 20))
            lines.append(
                f"  {label:20} {human:>6} · AI {cost_str(ev.ai_cost_usd):>8} · "
                f"shipped {ev.shipped}/{ev.sessions} · conf {escape(ev.confidence)}"
            )

        # --- Leakage funnel + the exact one-command fix ------------------
        leaks = leakage(unattributed_log_path())
        if leaks:
            lines.extend(["", "Leakage (adrift)"])
            for lk in leaks[:4]:
                remote = escape(truncate(lk.remote, 40))
                lines.append(f"  {remote}  {cost_str(lk.cost_usd)} ({lk.sessions})")
                lines.append(f"    → {escape(lk.fix_command)}")

        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)
