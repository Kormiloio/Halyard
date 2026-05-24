"""Tests for v5.0 Duplicate-Effort Detection logic."""

from __future__ import annotations

from datetime import datetime

import pytest

from halyard.ai_log import AiSession
from halyard.collisions import calculate_overlap_seconds, find_collisions


@pytest.fixture
def history():
    # Base session: project=Halyard, remote=kormilo/halyard, branch=main
    return [
        AiSession(
            start=datetime(2026, 5, 23, 10, 0, 0),
            end=datetime(2026, 5, 23, 10, 10, 0),
            tool="tool-1",
            model="model-1",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.01,
            remote="kormilo/halyard",
            branch="main",
        )
    ]


def test_collision_concurrent_full_overlap(history):
    # Session exactly matches history[0]
    session = AiSession(
        start=datetime(2026, 5, 23, 10, 0, 0),
        end=datetime(2026, 5, 23, 10, 10, 0),
        tool="tool-2",  # different tool
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        remote="kormilo/halyard",
        branch="main",
    )

    collisions = find_collisions(session, history)
    assert len(collisions) == 1
    assert collisions[0].tool == "tool-1"
    assert calculate_overlap_seconds(session, collisions[0]) == 600


def test_collision_partial_overlap(history):
    # Session starts halfway through history[0]
    session = AiSession(
        start=datetime(2026, 5, 23, 10, 5, 0),
        end=datetime(2026, 5, 23, 10, 15, 0),
        tool="tool-2",
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        remote="kormilo/halyard",
        branch="main",
    )

    collisions = find_collisions(session, history)
    assert len(collisions) == 1
    assert calculate_overlap_seconds(session, collisions[0]) == 300


def test_collision_sequential_within_threshold(history):
    # Session starts 5 minutes after history[0] ends (Threshold is 15m)
    session = AiSession(
        start=datetime(2026, 5, 23, 10, 15, 0),
        end=datetime(2026, 5, 23, 10, 20, 0),
        tool="tool-2",
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        remote="kormilo/halyard",
        branch="main",
    )

    collisions = find_collisions(session, history)
    assert len(collisions) == 1
    assert calculate_overlap_seconds(session, collisions[0]) == 0


def test_no_collision_different_branch(history):
    session = AiSession(
        start=datetime(2026, 5, 23, 10, 0, 0),
        end=datetime(2026, 5, 23, 10, 10, 0),
        tool="tool-2",
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        remote="kormilo/halyard",
        branch="other-branch",
    )

    collisions = find_collisions(session, history)
    assert len(collisions) == 0


def test_no_collision_large_gap(history):
    # Session starts 30 minutes after history[0] ends
    session = AiSession(
        start=datetime(2026, 5, 23, 10, 40, 0),
        end=datetime(2026, 5, 23, 10, 50, 0),
        tool="tool-2",
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        remote="kormilo/halyard",
        branch="main",
    )

    collisions = find_collisions(session, history)
    assert len(collisions) == 0


def test_find_collisions_ignores_self():
    s = AiSession(
        start=datetime(2026, 5, 23, 10, 0, 0),
        end=datetime(2026, 5, 23, 10, 10, 0),
        tool="tool-1",
        model="model-1",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        remote="repo",
        branch="main",
    )
    s._raw_hash = "abc123456789"

    # History contains the EXACT same session
    assert len(find_collisions(s, [s])) == 0


def _sess(tool: str, h: int, m0: int, m1: int, *, branch: str, remote: str = "repo") -> AiSession:
    return AiSession(
        start=datetime(2026, 5, 23, h, m0, 0),
        end=datetime(2026, 5, 23, h, m1, 0),
        tool=tool,
        model="m",
        input_tokens=1,
        output_tokens=1,
        cost_usd=0.0,
        remote=remote,
        branch=branch,
        project="acme:web",
    )


def test_detect_collisions_groups_by_branch_and_counts():
    from halyard.reports import detect_collisions

    sessions = [
        # main: two overlapping → both collide
        _sess("claude-code", 10, 0, 10, branch="main"),
        _sess("cursor", 10, 5, 15, branch="main"),
        # feature: single session, no overlap → not a collision
        _sess("claude-code", 11, 0, 10, branch="feature"),
        # no branch/remote → ignored
        AiSession(
            start=datetime(2026, 5, 23, 12, 0, 0),
            end=datetime(2026, 5, 23, 12, 5, 0),
            tool="x",
            model="m",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
        ),
    ]

    result = detect_collisions(sessions)

    assert len(result) == 1
    coll = result[0]
    assert coll.branch == "main"
    assert coll.count == 2
    assert coll.tools == ["claude-code", "cursor"]
    assert coll.project == "acme:web"


def test_detect_collisions_empty_when_no_overlap():
    from halyard.reports import detect_collisions

    sessions = [
        _sess("claude-code", 10, 0, 10, branch="main"),
        _sess("cursor", 14, 0, 10, branch="main"),  # hours later, no overlap
    ]

    assert detect_collisions(sessions) == []
