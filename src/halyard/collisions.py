"""Core logic for detecting overlapping AI effort (collisions)."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from halyard.ai_log import AiSession

# Sequential collision threshold: if a new session starts within this window
# after a previous session ended on the same branch, it's considered a collision.
SEQUENTIAL_THRESHOLD = timedelta(minutes=15)


def find_collisions(
    session: AiSession, history: list[AiSession], *, threshold: timedelta = SEQUENTIAL_THRESHOLD
) -> list[AiSession]:
    """Return sessions from history that 'collide' with the given session.

    A collision is defined as:
    1. Matching git remote AND matching git branch.
    2. Overlapping time intervals OR starting within `threshold` of the end.
    """
    if not session.remote or not session.branch:
        return []

    collisions = []
    for other in history:
        # Ignore self
        if other is session:
            continue

        h_other = getattr(other, "_raw_hash", None)
        h_session = getattr(session, "_raw_hash", None)
        if h_other is not None and h_session is not None and h_other == h_session:
            continue

        # 1. Identity Check (Remote + Branch)
        if other.remote != session.remote or other.branch != session.branch:
            continue

        # 2. Timing Check
        if _is_timing_collision(session, other, threshold):
            collisions.append(other)

    return collisions


def _is_timing_collision(a: AiSession, b: AiSession, threshold: timedelta) -> bool:
    """True if session A and B overlap or are within the threshold."""
    # Ensure A is the later one if they don't overlap
    first, second = (a, b) if a.start < b.start else (b, a)

    # Overlap? (First ends after second starts)
    if first.end > second.start:
        return True

    # Sequential within threshold?
    return (second.start - first.end) <= threshold


def calculate_overlap_seconds(a: AiSession, b: AiSession) -> int:
    """Return the number of seconds two sessions overlap."""
    latest_start = max(a.start, b.start)
    earliest_end = min(a.end, b.end)

    delta = (earliest_end - latest_start).total_seconds()
    return int(max(0, delta))
