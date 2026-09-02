"""v5.27 — the catch-up watermark deadlock.

`handle_stop_hook` anchors a row's start to the last recorded end for the
session (v3.9 catch-up). Unbounded, a gap longer than
``_MAX_SESSION_SECONDS`` makes the row fail ``session_is_implausible``, so
no row is written, so the watermark never advances, so the next row fails
identically. Capture for that session id dies permanently and silently.

Observed on a real machine: 14 days of capture lost while hooks, binary
and ``doctor`` all reported healthy.

The invariant these tests defend: **a guard that rejects a row must never
also prevent the next row from being valid.**
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard.ai_log import AiSession, parse_sessions
from halyard.collectors import (
    _MAX_SESSION_SECONDS,
    session_has_evidence,
    session_is_implausible,
)
from halyard.collectors.claude_code import _CATCHUP_MAX_REACH

_SID = "d4fb828b-529d-47a0-b120-1a862e72a732"


def _project(tmp_path: Path) -> Path:
    p = tmp_path / "project"
    p.mkdir(parents=True, exist_ok=True)
    (p / "halyard.toml").write_text("[project]\nslug = 'test'\n", encoding="utf-8")
    (p / "ai-sessions.log").write_text("; Halyard AI session log\n", encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import halyard.collectors.claude_code as cc

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)  # v5.24 guard: collectors resolve from cwd
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(cc, "_CC_SESSION_FILE", home / ".halyard" / "cc-session")


def _write_transcript(tmp_path: Path, *, turns: int, end: datetime) -> Path:
    """A transcript whose turns land in the hour before ``end``."""
    path = tmp_path / "transcript.jsonl"
    records = []
    for i in range(turns):
        ts = (end - timedelta(minutes=turns - i)).astimezone().isoformat()
        records.append(
            {
                "type": "assistant",
                "timestamp": ts,
                "message": {
                    "model": "claude-opus-5",
                    "usage": {"input_tokens": 10, "output_tokens": 500},
                },
            }
        )
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


# --- the deadlock itself ---------------------------------------------------


def test_unclamped_catchup_would_be_rejected() -> None:
    """Documents the defect: the raw watermark span fails the guard.

    This is the state the shipped code produced — evidence present, row
    still dropped, watermark left unadvanced.
    """
    watermark = datetime(2026, 8, 10, 22, 37, 22)
    now = datetime(2026, 8, 25, 9, 38)

    s = AiSession(
        start=watermark,
        end=now,
        tool="claude-code",
        model="claude-opus-5",
        input_tokens=164,
        output_tokens=82060,
        cost_usd=0.0,
    )
    assert session_has_evidence(s) is True
    assert session_is_implausible(s, now=now) is True, (
        "a >12h catch-up span is rejected — and with it the watermark advance"
    )


def test_catchup_reach_cannot_exceed_the_plausibility_limit() -> None:
    """The clamp and the guard must not be able to drift apart."""
    reach_seconds = _CATCHUP_MAX_REACH.total_seconds()
    assert reach_seconds <= _MAX_SESSION_SECONDS


def test_clamped_catchup_is_always_writable() -> None:
    """The fix: however old the watermark, the clamped row stays plausible."""
    now = datetime(2026, 8, 25, 9, 38)
    for days_stale in (1, 14, 365):
        watermark = now - timedelta(days=days_stale)
        start = max(watermark, now - _CATCHUP_MAX_REACH)

        s = AiSession(
            start=start,
            end=now,
            tool="claude-code",
            model="claude-opus-5",
            input_tokens=10,
            output_tokens=500,
            cost_usd=0.0,
        )
        assert not session_is_implausible(s, now=now), (
            f"a {days_stale}-day-old watermark must still yield a writable row"
        )


def test_recent_watermark_is_not_clamped() -> None:
    """No regression to v3.9: a normal gap still back-fills from the watermark."""
    now = datetime(2026, 8, 25, 9, 38)
    watermark = now - timedelta(hours=2)
    assert max(watermark, now - _CATCHUP_MAX_REACH) == watermark


# --- end-to-end: the watermark must advance --------------------------------


def test_stop_hook_writes_a_row_and_advances_past_a_stale_watermark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression that would have caught this bug.

    A session whose newest row is 14 days old must still capture its next
    turn, and the row it writes must move the watermark forward — otherwise
    the next turn deadlocks identically.
    """
    import halyard.collectors.claude_code as cc

    project = _project(tmp_path)
    now = datetime.now()
    stale_end = now - timedelta(days=14)

    # Seed a hook row 14 days old for this session id — the poisoned state.
    seed = AiSession(
        start=stale_end - timedelta(minutes=5),
        end=stale_end,
        tool="claude-code",
        model="claude-opus-5",
        input_tokens=10,
        output_tokens=100,
        cost_usd=0.0,
        session_id=_SID,
        source="hook",
    )
    from halyard.ai_log import append_session

    append_session(project, seed)
    assert cc._last_recorded_end(project, _SID) is not None

    transcript = _write_transcript(tmp_path, turns=3, end=now)
    monkeypatch.setattr(
        cc,
        "_read_payload",
        lambda: {
            "session_id": _SID,
            "transcript_path": str(transcript),
            "hook_event_name": "Stop",
        },
    )
    monkeypatch.chdir(project)

    assert cc.handle_stop_hook() == 0

    rows = [r for r in parse_sessions(project) if r.tool == "claude-code"]
    assert len(rows) >= 2, "the stale watermark must not suppress the new row"

    newest = max(r.end for r in rows)
    assert newest > stale_end, "the watermark must advance, or the next turn deadlocks"

    written = max(rows, key=lambda r: r.end)
    span = (written.end - written.start).total_seconds()
    assert span <= _MAX_SESSION_SECONDS, "a catch-up row must never claim an implausible span"
