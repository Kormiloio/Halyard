"""Shared leverage calc — the single source for "did the AI work ship?".

The web dashboard's `_leverage_panel` and the TUI `LeveragePane` both
derive their numbers from `summarize()`, so the two surfaces can never
disagree. Pure read over `pr_state` Halyard already captures; no writes,
no new fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from halyard.ai_log import AiSession

LEVERAGE_WINDOW_DAYS = 30


@dataclass(frozen=True)
class LeverageSummary:
    total: int
    merged: int
    open_: int
    closed: int
    none: int
    unsynced: int
    pct: int


def summarize(sessions: list[AiSession], now: datetime) -> LeverageSummary:
    """Engineering-outcome rollup over the trailing 30 days.

    ``pct`` is merged / total as an int; ``unsynced`` counts sessions
    whose ``pr_state`` has not been resolved yet (falsy state).
    """
    cutoff = now - timedelta(days=LEVERAGE_WINDOW_DAYS)
    recent = [s for s in sessions if s.start >= cutoff]
    total = len(recent)
    merged = sum(1 for s in recent if s.pr_state == "merged")
    open_ = sum(1 for s in recent if s.pr_state == "open")
    closed = sum(1 for s in recent if s.pr_state == "closed")
    none = sum(1 for s in recent if s.pr_state == "none")
    unsynced = sum(1 for s in recent if not s.pr_state)
    pct = int((merged / total) * 100) if total else 0
    return LeverageSummary(
        total=total,
        merged=merged,
        open_=open_,
        closed=closed,
        none=none,
        unsynced=unsynced,
        pct=pct,
    )
