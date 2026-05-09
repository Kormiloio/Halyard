"""Friends of the Sea / voyage roster widget."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.voyages import STAGE_LABELS, build_voyage_summaries


class VoyagePane(Static):
    """Render project voyage progress."""

    last_rendered_text = ""

    def render_voyages(self, project_dir: Path, sessions: list[AiSession]) -> None:
        sessions_by_project: dict[str, list[AiSession]] = {}
        for session in sessions:
            if session.project:
                sessions_by_project.setdefault(session.project, []).append(session)

        summaries = build_voyage_summaries(project_dir, sessions_by_project)
        if not summaries:
            self.last_rendered_text = "⛵ Voyage Roster\n\nNo voyages yet."
            self.update(self.last_rendered_text)
            return

        moored = sum(1 for v in summaries if v.stage == "moored")
        lines = ["⛵ Voyage Roster", f"{len(summaries)} projects · {moored} moored", ""]
        for summary in summaries[:6]:
            label = STAGE_LABELS.get(summary.stage, summary.stage)
            if summary.stage == "moored":
                creature = summary.creature or "·"
                trait = f" {summary.creature_trait}" if summary.creature_trait else ""
                lines.append(f"{creature} {summary.slug}  {label}{trait}")
            else:
                bar = _progress_bar(summary.progress_pct)
                lines.append(
                    f"· {summary.slug}  {label}  {summary.session_count}/{summary.target_sessions}"
                )
                lines.append(f"  {bar}")
        if len(summaries) > 6:
            lines.append(f"... +{len(summaries) - 6} more")

        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)


def _progress_bar(percent: int) -> str:
    filled = min(12, max(0, round(percent / 100 * 12)))
    return "▓" * filled + "░" * (12 - filled)
