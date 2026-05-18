"""Shared leverage calc — the single source for "did the AI work ship?".

The web dashboard's `_leverage_panel` and the TUI `LeveragePane` both
derive their numbers from `summarize()`, so the two surfaces can never
disagree. Pure read over `pr_state` Halyard already captures; no writes,
no new fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from halyard.ai_log import AiSession

LEVERAGE_WINDOW_DAYS = 30


def humanize_seconds(secs: int) -> str:
    """Compact human duration: '45m', '3h 12m', '2d 4h'. Integers only."""
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        h, rem = divmod(secs, 3600)
        m = rem // 60
        return f"{h}h {m}m" if m else f"{h}h"
    d, rem = divmod(secs, 86400)
    h = rem // 3600
    return f"{d}d {h}h" if h else f"{d}d"


def _median_int(values: list[int]) -> int | None:
    return round(median(values)) if values else None


@dataclass(frozen=True)
class LeverageSummary:
    total: int
    merged: int
    open_: int
    closed: int
    none: int
    unsynced: int
    pct: int
    # v3.1 review-friction medians over the window (None when no data).
    median_time_to_merge_s: int | None = None
    median_review_comments: int | None = None


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
    ttm = [s.time_to_merge_s for s in recent if s.time_to_merge_s is not None]
    rc = [s.review_comments for s in recent if s.review_comments is not None]
    return LeverageSummary(
        total=total,
        merged=merged,
        open_=open_,
        closed=closed,
        none=none,
        unsynced=unsynced,
        pct=pct,
        median_time_to_merge_s=_median_int(ttm),
        median_review_comments=_median_int(rc),
    )
