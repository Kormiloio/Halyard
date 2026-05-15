"""Tests for v3.0 repeated-attempt branch heuristic."""

from __future__ import annotations

from datetime import datetime

from halyard.ai_log import AiSession
from halyard.attempt_tracker import attempts_by_branch, repeated_attempt_count


def _s(branch: str | None) -> AiSession:
    return AiSession(
        start=datetime(2026, 5, 14, 10),
        end=datetime(2026, 5, 14, 10, 30),
        tool="claude-code",
        model="sonnet",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0,
        branch=branch,
    )


def test_branchless_session_is_zero() -> None:
    s = _s(None)
    assert repeated_attempt_count(s, [s]) == 0


def test_unique_branch_is_one() -> None:
    s = _s("feat/AUTH-1")
    assert repeated_attempt_count(s, [s]) == 1


def test_iteration_suffixes_collapse() -> None:
    """Common iteration suffixes collapse onto the same logical branch."""
    a = _s("feat/AUTH-1")
    b = _s("feat/AUTH-1-v2")
    c = _s("feat/AUTH-1-take2")
    d = _s("feat/AUTH-1-rebased")
    all_ = [a, b, c, d]
    assert repeated_attempt_count(a, all_) == 4
    assert repeated_attempt_count(d, all_) == 4


def test_different_tickets_do_not_collapse() -> None:
    a = _s("feat/AUTH-1")
    b = _s("feat/AUTH-2")
    assert repeated_attempt_count(a, [a, b]) == 1


def test_case_insensitive_match() -> None:
    a = _s("feat/AUTH-1")
    b = _s("FEAT/AUTH-1")
    assert repeated_attempt_count(a, [a, b]) == 2


def test_attempts_by_branch_aggregation() -> None:
    sessions = [
        _s("feat/AUTH-1"),
        _s("feat/AUTH-1-v2"),
        _s("feat/AUTH-2"),
        _s(None),
    ]
    counts = attempts_by_branch(sessions)
    # AUTH-1 + AUTH-1-v2 collapse → 2; AUTH-2 → 1; None excluded.
    assert sum(counts.values()) == 3
    assert max(counts.values()) == 2
