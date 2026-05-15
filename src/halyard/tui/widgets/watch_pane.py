"""Current watch / proof status widget."""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from pathlib import Path

from rich.markup import escape
from textual.widgets import Static

from halyard.ai_log import AiSession
from halyard.reports import ActiveTimer, read_active_timer
from halyard.tui.formatters import cost_str


class WatchPane(Static):
    """Render the active watch and proof state."""

    last_rendered_text = ""

    def render_watch(self, project_dir: Path, sessions: list[AiSession]) -> None:
        active = _active_for_project(project_dir)
        if active is None:
            self.last_rendered_text = _idle_watch_text(sessions)
            self.update(self.last_rendered_text)
            return

        watch_sessions = _sessions_since_start(sessions, active)
        attributed = sum(1 for s in watch_sessions if s.project)
        total = len(watch_sessions)
        adrift = total - attributed
        cost = sum(s.cost_usd for s in watch_sessions)
        proof, proof_label = _proof_label(watch_sessions)
        manifest = f"{attributed}/{total} in manifest" if total else "no sessions yet"

        lines = [
            "🔔 Current Watch",
            f"Making way · {escape(active.slug)}",
            f"Elapsed   {active.elapsed_label}",
            f"Sessions  {total}  {manifest}",
            f"Proof     {proof}  {proof_label}",
            f"Cost      {cost_str(cost)}",
        ]
        if adrift:
            lines.append(f"Adrift    {adrift}  · · · — — — · · ·")
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)


def _idle_watch_text(sessions: list[AiSession]) -> str:
    total = len(sessions)
    attributed = sum(1 for s in sessions if s.project)
    adrift = total - attributed
    proof, proof_label = _proof_label(sessions)
    lines = [
        "⚓ Current Watch",
        "At anchor",
        f"Sessions  {total}",
        f"Proof     {proof}  {proof_label}",
    ]
    if adrift:
        lines.append(f"Adrift    {adrift}  · · · — — — · · ·")
    else:
        lines.append("Manifest  clean")
    return "\n".join(lines)


def _active_for_project(project_dir: Path) -> ActiveTimer | None:
    active = read_active_timer()
    if active is None or active.timeclock is None:
        return None
    with suppress(ValueError):
        active.timeclock.resolve().relative_to(project_dir.resolve())
        return active
    return None


def _sessions_since_start(sessions: list[AiSession], active: ActiveTimer) -> list[AiSession]:
    if not active.started:
        return []
    with suppress(ValueError):
        started = datetime.strptime(active.started, "%Y-%m-%d %H:%M:%S")
        return [s for s in sessions if s.start >= started]
    return []


def _proof_label(sessions: list[AiSession]) -> tuple[str, str]:
    total = len(sessions)
    if total == 0:
        return "—", "not underway"
    attributed = sum(1 for s in sessions if s.project)
    with_tokens = sum(1 for s in sessions if s.tokens_available)
    score = round((attributed / total * 0.6 + with_tokens / total * 0.4) * 100)
    if score >= 80:
        return f"{score}%", "client-ready"
    if score >= 60:
        return f"{score}%", "review needed"
    return f"{score}%", "gaps present"
