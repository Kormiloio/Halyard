"""Halyard honors — ranks, stripes, medals, and service record computation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from halyard.ai_log import AiSession
from halyard.reports import parse_timeclock

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RankDef:
    level: int  # 0 = Civilian (unranked), 1-7 earned ranks
    name: str
    short: str  # displayed in tight spaces
    icon: str
    flavor: str
    description: str
    sessions_required: int  # total attributed sessions needed


@dataclass(frozen=True)
class Medal:
    key: str
    name: str
    icon: str
    description: str  # brief label
    detail: str  # shown when user clicks the name


@dataclass(frozen=True)
class PassportStamp:
    tool: str
    name: str
    icon: str


@dataclass(frozen=True)
class ServiceRecord:
    # Identity
    rank: RankDef
    next_rank: RankDef | None
    sessions_toward_next: int  # how many more attributed sessions until next rank

    # Stripes (reliability/consistency)
    watch_streak: int  # consecutive calendar days with ≥1 completed watch
    clean_watches: int  # watches where all sessions are attributed + have tokens
    total_watches: int
    gold_stripe_earned: bool  # 30+ consecutive clean-watch days

    # Medals
    earned_medals: list[Medal]

    # Passport
    passport: list[PassportStamp]

    # Raw stats used for display
    total_sessions: int
    attributed_sessions: int
    proof_score: int  # 0-100


# ---------------------------------------------------------------------------
# Rank catalog  (level 0 is the "not yet" state)
# ---------------------------------------------------------------------------

RANKS: list[RankDef] = [
    RankDef(
        level=0,
        name="Civilian",
        short="Civilian",
        icon="⚓",
        flavor="Not yet enlisted.",
        description="You haven't started tracking yet. Run halyard start to begin.",
        sessions_required=0,
    ),
    RankDef(
        level=1,
        name="Deckhand",
        short="Deckhand",
        icon="🪢",
        flavor="First lines cast. The work begins.",
        description="You've logged your first AI sessions. The voyage has started.",
        sessions_required=1,
    ),
    RankDef(
        level=2,
        name="Able Seafarer",
        short="Seafarer",
        icon="⛵",
        flavor="You know these waters.",
        description="Ten attributed sessions. You're building a reliable practice.",
        sessions_required=10,
    ),
    RankDef(
        level=3,
        name="Quartermaster",
        short="Quartermaster",
        icon="📋",
        flavor="The manifest is your responsibility.",
        description="Fifty attributed sessions. You keep clean records.",
        sessions_required=50,
    ),
    RankDef(
        level=4,
        name="Navigator",
        short="Navigator",
        icon="🧭",
        flavor="You set the course.",
        description="One hundred attributed sessions. You navigate with confidence.",
        sessions_required=100,
    ),
    RankDef(
        level=5,
        name="First Mate",
        short="First Mate",
        icon="🔭",
        flavor="The ship runs because of you.",
        description="Two hundred fifty attributed sessions. Trusted with the watch.",
        sessions_required=250,
    ),
    RankDef(
        level=6,
        name="Captain",
        short="Captain",
        icon="🎖️",
        flavor="All hands know your name.",
        description=(
            "Five hundred attributed sessions. A full calendar month, every session attributed."
        ),
        sessions_required=500,
    ),
    RankDef(
        level=7,
        name="Commodore",
        short="Commodore",
        icon="🏅",
        flavor="A fleet, not just a ship.",
        description=(
            "One thousand attributed sessions across 3+ projects. "
            "You command a clean, documented fleet."
        ),
        sessions_required=1000,
    ),
]

# Map level → RankDef for fast lookup
_RANK_BY_LEVEL: dict[int, RankDef] = {r.level: r for r in RANKS}


# ---------------------------------------------------------------------------
# Medal catalog
# ---------------------------------------------------------------------------

MEDALS: list[Medal] = [
    Medal(
        key="eight_bells",
        name="Eight Bells",
        icon="🔔",
        description="Completed your first watch",
        detail=(
            "Eight bells marks the end of a naval watch. "
            "You completed your first halyard start → stop cycle."
        ),
    ),
    Medal(
        key="full_sail",
        name="Full Sail",
        icon="⛵",
        description="Completed a 90-minute deep-work session",
        detail=(
            "Full sail means every sail set and drawing. "
            "You ran a timer for 90 minutes without breaking off."
        ),
    ),
    Medal(
        key="clean_manifest",
        name="Order of the Clean Manifest",
        icon="📋",
        description="Ended a day with zero sessions adrift",
        detail=(
            "A clean manifest means every session is attributed and documented. "
            "You closed the day with nothing adrift."
        ),
    ),
    Medal(
        key="lighthouse",
        name="Lighthouse",
        icon="🏮",
        description="Used halyard backfill to rescue lost sessions",
        detail=(
            "A lighthouse guides ships that have lost their way. "
            "You used backfill attribution to recover sessions that had gone adrift."
        ),
    ),
    Medal(
        key="signal_master",
        name="Signal Master",
        icon="🚩",
        description="Used 3 or more distinct AI tools",
        detail=(
            "Signal flags identify every vessel in the fleet. "
            "You've captured sessions from 3 or more different AI tools."
        ),
    ),
    Medal(
        key="harbor_master",
        name="Harbor Master",
        icon="⚓",
        description="Generated your first invoice",
        detail=(
            "The harbor master oversees every vessel in port. "
            "You generated an invoice — your proof is ready to bill."
        ),
    ),
    Medal(
        key="fair_winds",
        name="Fair Winds",
        icon="🌬️",
        description="7-day watch streak with all sessions attributed",
        detail=(
            "Fair winds and following seas — the sailor's blessing. "
            "You kept a clean manifest for 7 consecutive days."
        ),
    ),
    Medal(
        key="rescue",
        name="Rescue at Sea",
        icon="🆘",
        description="Cleared all adrift sessions after having >5",
        detail=(
            "Every sailor knows the code: you never leave someone adrift. "
            "You cleared a backlog of 5 or more unattributed sessions."
        ),
    ),
]

_MEDAL_BY_KEY: dict[str, Medal] = {m.key: m for m in MEDALS}


# ---------------------------------------------------------------------------
# Watch extraction
# ---------------------------------------------------------------------------


@dataclass
class _Watch:
    slug: str
    start: datetime
    end: datetime
    duration_minutes: float


def _extract_watches(project_dir: Path) -> list[_Watch]:
    """Parse completed timeclock i/o pairs into Watch objects."""
    entries = parse_timeclock(project_dir / "time.timeclock")
    watches: list[_Watch] = []
    for start, end, account in entries:
        duration = (end - start).total_seconds() / 60
        watches.append(_Watch(slug=account, start=start, end=end, duration_minutes=duration))
    return watches


# ---------------------------------------------------------------------------
# Streak helpers
# ---------------------------------------------------------------------------


def _watch_streak(watches: list[_Watch], *, as_of: date | None = None) -> int:
    """Return the current consecutive-day watch streak ending on or before as_of."""
    today = as_of or date.today()
    watch_dates: set[date] = {w.start.date() for w in watches}
    streak = 0
    cursor = today
    while cursor in watch_dates:
        streak += 1
        cursor = (
            date(cursor.year, cursor.month, cursor.day - 1)
            if cursor.day > 1
            else date(
                cursor.year - 1 if cursor.month == 1 else cursor.year,
                12 if cursor.month == 1 else cursor.month - 1,
                31
                if cursor.month == 1
                else _days_in_month(
                    cursor.year - 1 if cursor.month == 1 else cursor.year,
                    12 if cursor.month == 1 else cursor.month - 1,
                ),
            )
        )
    return streak


def _days_in_month(year: int, month: int) -> int:
    import calendar

    return calendar.monthrange(year, month)[1]


def _clean_watch_days(
    watches: list[_Watch],
    sessions: list[AiSession],
) -> set[date]:
    """Return dates where every session overlapping a watch is attributed + has tokens."""
    watch_dates: set[date] = set()
    for watch in watches:
        day = watch.start.date()
        day_sessions = [
            s
            for s in sessions
            if s.start.date() == day or (s.start >= watch.start and s.end <= watch.end)
        ]
        if not day_sessions:
            continue
        if all(s.project and s.tokens_available for s in day_sessions):
            watch_dates.add(day)
    return watch_dates


def _clean_watch_streak(clean_days: set[date], *, as_of: date | None = None) -> int:
    today = as_of or date.today()
    streak = 0
    cursor = today
    while cursor in clean_days:
        streak += 1
        cursor = _prev_day(cursor)
    return streak


def _prev_day(d: date) -> date:
    import calendar

    if d.day > 1:
        return date(d.year, d.month, d.day - 1)
    if d.month > 1:
        return date(d.year, d.month - 1, calendar.monthrange(d.year, d.month - 1)[1])
    return date(d.year - 1, 12, 31)


# ---------------------------------------------------------------------------
# Rank evaluation
# ---------------------------------------------------------------------------


def _evaluate_rank(attributed_count: int) -> tuple[RankDef, RankDef | None, int]:
    """Return (current_rank, next_rank_or_None, sessions_until_next)."""
    current = RANKS[0]
    for rank in RANKS[1:]:
        if attributed_count >= rank.sessions_required:
            current = rank
        else:
            return current, rank, rank.sessions_required - attributed_count
    return current, None, 0


# ---------------------------------------------------------------------------
# Medal evaluation
# ---------------------------------------------------------------------------


def _evaluate_medals(
    project_dir: Path,
    sessions: list[AiSession],
    watches: list[_Watch],
    clean_days: set[date],
) -> list[Medal]:
    earned: list[str] = []

    # Eight Bells — completed at least one watch
    if watches:
        earned.append("eight_bells")

    # Full Sail — at least one watch ≥ 90 minutes
    if any(w.duration_minutes >= 90 for w in watches):
        earned.append("full_sail")

    # Clean Manifest — at least one day with zero adrift
    if clean_days:
        earned.append("clean_manifest")

    # Lighthouse — any session attributed via backfill
    if any(s.attr_method == "backfill" for s in sessions):
        earned.append("lighthouse")

    # Signal Master — 3+ distinct AI tools
    tools_used = {s.tool for s in sessions}
    if len(tools_used) >= 3:
        earned.append("signal_master")

    # Harbor Master — invoice files exist
    invoice_dir = project_dir / "invoices"
    if invoice_dir.is_dir() and any(invoice_dir.iterdir()):
        earned.append("harbor_master")

    # Fair Winds — 7+ consecutive clean-watch days
    if _clean_watch_streak(clean_days) >= 7:
        earned.append("fair_winds")

    # Rescue at Sea — ever had ≥5 adrift, now has 0
    # We approximate: if there are 0 adrift now and there have been ≥5 attributed via backfill
    adrift_now = sum(1 for s in sessions if not s.project)
    backfilled = sum(1 for s in sessions if s.attr_method == "backfill")
    if adrift_now == 0 and backfilled >= 5:
        earned.append("rescue")

    return [_MEDAL_BY_KEY[k] for k in earned if k in _MEDAL_BY_KEY]


# ---------------------------------------------------------------------------
# Passport
# ---------------------------------------------------------------------------

PASSPORT_STAMPS: dict[str, tuple[str, str]] = {
    "claude-code": ("Claude Code", "🤖"),
    "cursor": ("Cursor", "🖱️"),
    "gemini-cli": ("Gemini CLI", "♊"),
    "codex": ("Codex", "📦"),
    "manual": ("Manual", "✏️"),
}
_PASSPORT_DEFAULT_ICON = "🔧"


def _evaluate_passport(sessions: list[AiSession]) -> list[PassportStamp]:
    seen: dict[str, PassportStamp] = {}
    for s in sessions:
        if s.tool not in seen:
            name, icon = PASSPORT_STAMPS.get(s.tool, (s.tool, _PASSPORT_DEFAULT_ICON))
            seen[s.tool] = PassportStamp(tool=s.tool, name=name, icon=icon)
    return list(seen.values())


# ---------------------------------------------------------------------------
# Proof score
# ---------------------------------------------------------------------------


def _compute_proof_score(sessions: list[AiSession]) -> int:
    total = len(sessions)
    if total == 0:
        return 100
    attributed = sum(1 for s in sessions if s.project)
    with_tokens = sum(1 for s in sessions if s.tokens_available)
    return round((attributed / total * 0.6 + with_tokens / total * 0.4) * 100)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_service_record(
    project_dir: Path,
    sessions: list[AiSession],
    *,
    as_of: date | None = None,
) -> ServiceRecord:
    """Compute the full service record from sessions + timeclock data."""
    attributed = [s for s in sessions if s.project]
    attributed_count = len(attributed)

    watches = _extract_watches(project_dir)
    clean_days = _clean_watch_days(watches, sessions)

    streak = _watch_streak(watches, as_of=as_of)
    cw_streak = _clean_watch_streak(clean_days, as_of=as_of)

    rank, next_rank, sessions_toward_next = _evaluate_rank(attributed_count)
    earned_medals = _evaluate_medals(project_dir, sessions, watches, clean_days)
    passport = _evaluate_passport(sessions)
    proof_score = _compute_proof_score(sessions)

    clean_watch_count = len(clean_days)
    gold_stripe_earned = cw_streak >= 30

    return ServiceRecord(
        rank=rank,
        next_rank=next_rank,
        sessions_toward_next=sessions_toward_next,
        watch_streak=streak,
        clean_watches=clean_watch_count,
        total_watches=len(watches),
        gold_stripe_earned=gold_stripe_earned,
        earned_medals=earned_medals,
        passport=passport,
        total_sessions=len(sessions),
        attributed_sessions=attributed_count,
        proof_score=proof_score,
    )
