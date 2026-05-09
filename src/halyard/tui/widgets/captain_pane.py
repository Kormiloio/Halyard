"""Captain's Quarters widget for ranks, stripes, medals, and passport."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from halyard.achievements import Medal, PassportStamp, RankDef, build_service_record
from halyard.ai_log import AiSession


class CaptainPane(Static):
    """Render terminal-sized honors state."""

    last_rendered_text = ""

    def render_record(self, project_dir: Path, sessions: list[AiSession]) -> None:
        record = build_service_record(project_dir, sessions)
        rank = record.rank

        lines = [
            "⚓ Captain's Quarters",
            f"{rank.icon} {rank.name}",
            rank.flavor,
            _rank_progress(record.attributed_sessions, record.next_rank),
            _stripes(record.watch_streak, record.gold_stripe_earned),
            (
                f"Proof {record.proof_score}%"
                f"  Manifest {record.attributed_sessions}/{record.total_sessions}"
            ),
            _passport_line(record.passport),
            _medals_line(record.earned_medals),
        ]
        self.last_rendered_text = "\n".join(lines)
        self.update(self.last_rendered_text)


def _rank_progress(attributed: int, next_rank: RankDef | None) -> str:
    if next_rank is None:
        return "Rank  highest achieved"
    return f"Rank  {attributed}/{next_rank.sessions_required} -> {next_rank.name}"


def _stripes(streak: int, gold: bool) -> str:
    count = min(4, streak // 7)
    bar = "▐" * count if count else "—"
    suffix = "  gold" if gold else ""
    return f"Stripes {bar}  {streak}d watch{suffix}"


def _passport_line(passport: list[PassportStamp]) -> str:
    if not passport:
        return "Passport  no ports yet"
    rendered = " ".join(f"{stamp.icon}{stamp.name}" for stamp in passport[:4])
    if len(passport) > 4:
        rendered += f" +{len(passport) - 4}"
    return f"Passport  {rendered}"


def _medals_line(medals: list[Medal]) -> str:
    if not medals:
        return "Medals  none yet"
    rendered = " ".join(f"{medal.icon}{medal.name}" for medal in medals[:3])
    if len(medals) > 3:
        rendered += f" +{len(medals) - 3}"
    return f"Medals  {rendered}"
