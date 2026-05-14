"""Friends of the Sea — voyage lifecycle and sea creature assignment."""

from __future__ import annotations

import os
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from halyard.ai_log import AiSession

VOYAGES_FILENAME = "voyages.toml"

# ---------------------------------------------------------------------------
# Stage vocabulary
# ---------------------------------------------------------------------------

STAGE_LABELS: dict[str, str] = {
    "not_started": "Not yet underway",
    "anchors_aweigh": "Anchors Aweigh",
    "making_headway": "Making Headway",
    "rounding_the_mark": "Rounding the Mark",
    "flying_colors": "Flying Colors",
    "moored": "Shipshape · Moored",
}

# ---------------------------------------------------------------------------
# Creature catalog
# ---------------------------------------------------------------------------

CREATURES: list[tuple[str, str]] = [
    ("🐋", "Massive project"),
    ("🐢", "Long voyage"),
    ("🐬", "Clean run"),
    ("🦑", "Multi-tool"),
    ("🐠", "Small but complete"),
    ("🦈", "Intense sprint"),
    ("🪸", "Ecosystem builder"),
    ("🦭", "Playful"),
]

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_DEFAULT_TARGET = 20
_DEFAULT_INACTIVITY = 14


@dataclass
class VoyageEntry:
    slug: str
    target_sessions: int = _DEFAULT_TARGET
    inactivity_days: int = _DEFAULT_INACTIVITY
    stage: str = "not_started"
    started_at: str = ""
    completed_at: str = ""
    creature: str = ""
    creature_trait: str = ""


# ---------------------------------------------------------------------------
# TOML read / write
# ---------------------------------------------------------------------------


def read_voyages(project_dir: Path) -> list[VoyageEntry]:
    path = project_dir / VOYAGES_FILENAME
    if not path.exists():
        return []
    import tomllib

    try:
        data = tomllib.loads(path.read_text())
    except Exception:
        return []

    entries: list[VoyageEntry] = []
    for row in data.get("voyage", []):
        if not isinstance(row, dict) or "slug" not in row:
            continue
        entries.append(
            VoyageEntry(
                slug=row["slug"],
                target_sessions=int(row.get("target_sessions", _DEFAULT_TARGET)),
                inactivity_days=int(row.get("inactivity_days", _DEFAULT_INACTIVITY)),
                stage=row.get("stage", "not_started"),
                started_at=row.get("started_at", ""),
                completed_at=row.get("completed_at", ""),
                creature=row.get("creature", ""),
                creature_trait=row.get("creature_trait", ""),
            )
        )
    return entries


def write_voyages(project_dir: Path, entries: list[VoyageEntry]) -> None:
    import tomli_w

    data: dict[str, list[dict[str, object]]] = {
        "voyage": [
            {
                "slug": e.slug,
                "target_sessions": e.target_sessions,
                "inactivity_days": e.inactivity_days,
                "stage": e.stage,
                "started_at": e.started_at,
                "completed_at": e.completed_at,
                "creature": e.creature,
                "creature_trait": e.creature_trait,
            }
            for e in entries
        ]
    }
    content = "# Halyard voyages — one entry per tracked project slug\n\n" + tomli_w.dumps(data)

    path = project_dir / VOYAGES_FILENAME
    fd, tmp = tempfile.mkstemp(dir=project_dir, prefix=".voyages-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        import contextlib

        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def voyage_for_slug(entries: list[VoyageEntry], slug: str) -> VoyageEntry:
    for e in entries:
        if e.slug == slug:
            return e
    return VoyageEntry(slug=slug)


# ---------------------------------------------------------------------------
# Stage computation
# ---------------------------------------------------------------------------


def compute_stage(session_count: int, target: int) -> str:
    if session_count == 0:
        return "not_started"
    pct = session_count / max(target, 1)
    if pct >= 1.0:
        return "moored"
    if pct >= 0.75:
        return "flying_colors"
    if pct >= 0.50:
        return "rounding_the_mark"
    if pct >= 0.25:
        return "making_headway"
    return "anchors_aweigh"


# ---------------------------------------------------------------------------
# Creature assignment
# ---------------------------------------------------------------------------


def assign_creature(
    slug: str,
    sessions: list[AiSession],
    all_completed_counts: dict[str, int],
    *,
    coral_reef: bool = False,
) -> tuple[str, str]:
    """Return (emoji, trait_name) for the project. First matching rule wins."""
    total = len(sessions)

    # 1. Whale — highest session count of all completed projects
    max_count = max(all_completed_counts.values(), default=0)
    if total > 0 and total >= max_count:
        return "🐋", "Massive project"

    # 2. Sea Turtle — spans 3+ calendar months
    if sessions:
        span_days = (sessions[-1].end - sessions[0].start).days
        if span_days >= 90:
            return "🐢", "Long voyage"

    # 3. Dolphin — large clean run (>15 sessions, all attributed)
    if total > 15 and sessions and all(s.project for s in sessions):
        return "🐬", "Clean run"

    # 4. Octopus — 3+ distinct tools
    if len({s.tool for s in sessions}) >= 3:
        return "🦑", "Multi-tool"

    # 5. Clownfish — small but complete (≤15 sessions, all attributed)
    if total <= 15 and sessions and all(s.project for s in sessions):
        return "🐠", "Small but complete"

    # 6. Shark — 5+ sessions in a single day
    if sessions:
        day_counts = Counter(s.start.date() for s in sessions)
        if max(day_counts.values(), default=0) >= 5:
            return "🦈", "Intense sprint"

    # 7. Coral Reef — 5+ concurrent active projects
    if coral_reef:
        return "🪸", "Ecosystem builder"

    # 8. Seal — fallback
    return "🦭", "Playful"


# ---------------------------------------------------------------------------
# Auto-complete detection
# ---------------------------------------------------------------------------


def check_auto_complete(
    project_dir: Path,
    sessions_by_project: dict[str, list[AiSession]],
    *,
    now: date | None = None,
) -> list[str]:
    """Detect newly-completed projects and write updates to voyages.toml.

    Returns slugs that were newly marked complete this call.
    """
    today = now or date.today()
    entries = read_voyages(project_dir)
    slug_map = {e.slug: e for e in entries}
    newly_complete: list[str] = []
    changed = False

    all_slugs = set(sessions_by_project) | {e.slug for e in entries}
    for slug in all_slugs:
        sessions = sessions_by_project.get(slug, [])
        entry = slug_map.get(slug) or VoyageEntry(slug=slug)

        if entry.stage == "moored":
            continue

        count = len(sessions)
        target = entry.target_sessions

        # Target hit
        auto_complete = count >= target

        # Inactivity trigger
        if not auto_complete and sessions:
            last_session_date = max(s.end.date() for s in sessions)
            if (today - last_session_date).days >= entry.inactivity_days:
                auto_complete = True

        if auto_complete and count > 0:
            all_completed = {
                e.slug: len(sessions_by_project.get(e.slug, []))
                for e in entries
                if e.stage == "moored"
            }
            all_completed[slug] = count
            coral_reef = _had_concurrent_projects(sessions_by_project, slug)
            emoji, trait = assign_creature(slug, sessions, all_completed, coral_reef=coral_reef)

            started = sessions[0].start.strftime("%Y-%m-%d") if sessions else ""
            entry.stage = "moored"
            entry.started_at = entry.started_at or started
            entry.completed_at = today.isoformat()
            entry.creature = emoji
            entry.creature_trait = trait
            slug_map[slug] = entry
            newly_complete.append(slug)
            changed = True
            continue

        # Update stage
        new_stage = compute_stage(count, target)
        if new_stage != entry.stage:
            if new_stage == "anchors_aweigh" and not entry.started_at:
                entry.started_at = sessions[0].start.strftime("%Y-%m-%d") if sessions else ""
            entry.stage = new_stage
            slug_map[slug] = entry
            changed = True

    if changed:
        write_voyages(project_dir, list(slug_map.values()))

    return newly_complete


def _had_concurrent_projects(
    sessions_by_project: dict[str, list[AiSession]],
    target_slug: str,
) -> bool:
    """Return True if the user had 5+ active projects on any single day."""
    day_projects: dict[date, set[str]] = {}
    for slug, sessions in sessions_by_project.items():
        for s in sessions:
            d = s.start.date()
            day_projects.setdefault(d, set()).add(slug)
    return any(len(projects) >= 5 for projects in day_projects.values())


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


@dataclass
class VoyageSummary:
    slug: str
    stage: str
    stage_label: str
    session_count: int
    target_sessions: int
    creature: str
    creature_trait: str
    completed_at: str
    progress_pct: int = field(init=False)

    def __post_init__(self) -> None:
        self.progress_pct = min(100, round(100 * self.session_count / max(self.target_sessions, 1)))


def build_voyage_summaries(
    project_dir: Path,
    sessions_by_project: dict[str, list[AiSession]],
) -> list[VoyageSummary]:
    entries = read_voyages(project_dir)
    slug_map = {e.slug: e for e in entries}
    all_slugs = sorted(set(sessions_by_project) | {e.slug for e in entries})
    summaries: list[VoyageSummary] = []
    for slug in all_slugs:
        entry = slug_map.get(slug) or VoyageEntry(slug=slug)
        count = len(sessions_by_project.get(slug, []))
        stage = "moored" if entry.stage == "moored" else compute_stage(count, entry.target_sessions)
        summaries.append(
            VoyageSummary(
                slug=slug,
                stage=stage,
                stage_label=STAGE_LABELS.get(stage, stage),
                session_count=count,
                target_sessions=entry.target_sessions,
                creature=entry.creature,
                creature_trait=entry.creature_trait,
                completed_at=entry.completed_at,
            )
        )
    return summaries
