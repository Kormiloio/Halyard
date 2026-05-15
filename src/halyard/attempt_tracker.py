"""Repeated-attempt heuristic for the v3.0 outcome graph.

Counts how many distinct sessions share the *same logical branch* within a
window. The heuristic is deliberately conservative — it strips a small set
of well-known suffixes that indicate iteration on the same ticket:

  feat/AUTH-123              )
  feat/AUTH-123-v2           )  same logical branch
  feat/AUTH-123-take2        )
  feat/AUTH-123-rebased      )

No source code, prompt text, or commit content is read. Only the
``branch`` field already present on each ``AiSession`` is consulted.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from halyard.ai_log import AiSession

# Suffixes that indicate iteration on the same logical branch, not a new
# branch. Stripped (case-insensitively) before grouping.
_ITERATION_SUFFIX_RE = re.compile(
    r"(?:[-_](?:v\d+|take\d+|rebased?|retry|attempt\d+|fix\d*|wip))+$",
    re.IGNORECASE,
)


def _normalize_branch(branch: str) -> str:
    """Strip iteration suffixes so retries collapse onto the same key."""
    return _ITERATION_SUFFIX_RE.sub("", branch).rstrip("-_").lower()


def attempts_by_branch(sessions: Iterable[AiSession]) -> dict[str, int]:
    """Return {normalized_branch: session_count} across the input.

    Sessions without a branch are skipped.
    """
    counts: dict[str, int] = defaultdict(int)
    for s in sessions:
        if not s.branch:
            continue
        counts[_normalize_branch(s.branch)] += 1
    return dict(counts)


def repeated_attempt_count(session: AiSession, all_sessions: Iterable[AiSession]) -> int:
    """How many sessions share *session*'s normalized branch (including itself)?

    Returns 0 if the session has no branch attached.
    """
    if not session.branch:
        return 0
    key = _normalize_branch(session.branch)
    return sum(1 for s in all_sessions if s.branch and _normalize_branch(s.branch) == key)
