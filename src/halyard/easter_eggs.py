"""Easter eggs and hidden delights for the nautically inclined."""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# ASCII art
# ---------------------------------------------------------------------------

_SHIP = r"""
              |    |    |
             )_)  )_)  )_)
            )___))___))___)\\
           )____)____)_____)\\
         _____|____|____|____\\___
    ~~~ /   HALYARD  · AI LEDGER  \\ ~~~
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ~~~   ~~~   ~~~~   ~~~   ~~~~   ~~~
"""

# ---------------------------------------------------------------------------
# Navigator's log quotes
# ---------------------------------------------------------------------------

_QUOTES: list[str] = [
    "The sea does not reward those who are too anxious, too greedy, or too impatient.",
    "Not all those who wander are lost — but check your attribution logs.",
    "A smooth sea never made a skilled navigator.",
    "Any sufficiently advanced AI session is indistinguishable from magic.",
    "The horizon is not the end of the world, just the limit of your context window.",
    "Fair winds and following seas, Captain.",
    "Log everything. The sea keeps no secrets, neither should your ledger.",
    "Every voyage begins with a single token.",
    "A ship in harbour is safe, but that is not what ships are for.",
    "The cost of AI is known. The value of the voyage — that is yours to prove.",
    "Even the mightiest galleon started with a single `halyard init`.",
    "To know where you are going, you must first know where you have been.",
    "The wind and the waves are always on the side of the ablest navigator.",
]


def random_quote() -> str:
    return random.choice(_QUOTES)


def ship_art() -> str:
    return _SHIP


# ---------------------------------------------------------------------------
# Morse SOS
# ---------------------------------------------------------------------------

_MORSE_SOS = "· · ·   — — —   · · ·"


def mayday_lines() -> list[str]:
    return [
        "",
        "  🚨  MAYDAY  MAYDAY  MAYDAY  🚨",
        "",
        f"     {_MORSE_SOS}",
        "",
        "  All hands on deck.",
        "  If you need help: halyard --help",
        "  If you're truly lost at sea: halyard ahoy",
        "",
    ]


# ---------------------------------------------------------------------------
# Pirate-speak translator (September 19 — Talk Like a Pirate Day)
# ---------------------------------------------------------------------------

_PIRATE_MAP: list[tuple[str, str]] = [
    ("hello", "ahoy"),
    ("hi ", "ahoy "),
    ("yes", "aye"),
    ("my ", "me "),
    ("you ", "ye "),
    ("your", "yer"),
    ("is ", "be "),
    ("are ", "be "),
    ("friend", "matey"),
    ("money", "doubloons"),
    ("dollars", "doubloons"),
    ("error", "kraken attack"),
    ("warning", "stormy waters"),
    ("project", "voyage"),
    ("session", "watch"),
    ("cost", "plunder"),
    ("report", "captain's log"),
    ("dashboard", "bridge"),
    ("data", "treasure"),
]


def is_pirate_day(now: datetime | None = None) -> bool:
    d = now or datetime.now()
    return d.month == 9 and d.day == 19


def pirate_speak(text: str) -> str:
    result = text
    for plain, arrr in _PIRATE_MAP:
        result = result.replace(plain, arrr)
        result = result.replace(plain.capitalize(), arrr.capitalize())
    return result


# ---------------------------------------------------------------------------
# Late-night message (00:00-04:59 local time)
# ---------------------------------------------------------------------------


def is_late_night(now: datetime | None = None) -> bool:
    return 0 <= (now or datetime.now()).hour < 5


_LATE_NIGHT_LINES: list[str] = [
    "Still at the helm, Captain? The night watch appreciates your dedication.",
    "Burning the midnight oil — or burning through tokens. Either way, carry on.",
    "The stars are out. So are you. Respect.",
    "Night watch in progress. All quiet on the digital sea.",
    "Even seasoned navigators rest. Just saying.",
]


def late_night_message() -> str:
    return random.choice(_LATE_NIGHT_LINES)


# ---------------------------------------------------------------------------
# Milestone detection
# ---------------------------------------------------------------------------

_MILESTONES_FILE = Path.home() / ".halyard" / "milestones-seen"

_SESSION_MILESTONES: list[int] = [100, 500, 1000, 5000]
_COST_MILESTONES: list[int] = [100, 500, 1000, 5000]

_RANKS: dict[int, str] = {
    100: "Able Seaman",
    500: "Boatswain",
    1000: "First Mate",
    5000: "Captain of the Watch",
}

_COST_LORE: dict[int, str] = {
    100: "A hundred doubloons in the ledger.",
    500: "Five hundred doubloons. The chest grows heavy.",
    1000: "A thousand doubloons. You're funding a fleet.",
    5000: "Five thousand doubloons. The treasure room is full.",
}


def _load_seen() -> set[str]:
    if not _MILESTONES_FILE.exists():
        return set()
    return {line.strip() for line in _MILESTONES_FILE.read_text().splitlines() if line.strip()}


def _save_seen(seen: set[str]) -> None:
    _MILESTONES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MILESTONES_FILE.write_text("\n".join(sorted(seen)) + "\n")


def check_milestones(session_count: int, total_cost: float) -> list[str]:
    """Return newly-triggered milestone messages (empty list if none)."""
    seen = _load_seen()
    messages: list[str] = []

    for n in _SESSION_MILESTONES:
        key = f"sessions:{n}"
        if session_count >= n and key not in seen:
            seen.add(key)
            rank = _RANKS.get(n, "")
            rank_suffix = f" Promoted to {rank}!" if rank else ""
            messages.append(f"⚓  {n} sessions logged!{rank_suffix}")

    for n in _COST_MILESTONES:
        key = f"cost:{n}"
        if total_cost >= n and key not in seen:
            seen.add(key)
            lore = _COST_LORE.get(n, f"${n} in AI spend logged.")
            messages.append(f"💰  {lore}")

    if messages:
        _save_seen(seen)

    return messages
