"""v3.14 — Gemini session de-duplication.

A live Gemini session was captured ~2.5x over: the hook writes the
whole-session cumulative total every turn, and the importer writes one
more whole-session row, so one session produced several overlapping rows.
The read-time collapse keeps one canonical row per session id.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from halyard.ai_log import (
    AI_LOG_FILENAME,
    AiSession,
    append_session,
    collapse_gemini_sessions,
    parse_sessions,
)

_SID = "70615981-d116-4180-a8d6-4d032b04166a"
_T = datetime(2026, 5, 23, 16, 8, 33)


def _gem(
    *,
    start: datetime,
    end: datetime,
    inp: int,
    out: int,
    cache: int,
    project: str | None = None,
    session_id: str | None = None,
    job_id: str | None = None,
    model: str = "gemini-3-flash-preview",
) -> AiSession:
    return AiSession(
        start=start,
        end=end,
        tool="gemini-cli",
        model=model,
        input_tokens=inp,
        output_tokens=out,
        cost_usd=0.0,
        cache_read=cache or None,
        project=project,
        session_id=session_id,
        job_id=job_id,
    )


def test_real_session_three_rows_collapse_to_one() -> None:
    """The exact 70615981 shape: two hook cumulative snapshots + one
    importer row collapse to one canonical row matching the /quit total."""
    rows = [
        # hook turn 1 (cumulative-so-far), attributed
        _gem(
            start=_T,
            end=_T + timedelta(seconds=99),
            inp=27246,
            out=88,
            cache=24698,
            project="kormilo/halyard",
            session_id=_SID,
        ),
        # hook turn 2 (full cumulative), attributed
        _gem(
            start=_T + timedelta(seconds=99),
            end=_T + timedelta(seconds=709),
            inp=59970,
            out=1451,
            cache=170196,
            project="kormilo/halyard",
            session_id=_SID,
        ),
        # importer row (full session, unattributed), job_id form
        _gem(
            start=_T,
            end=_T + timedelta(seconds=707),
            inp=59970,
            out=1451,
            cache=170196,
            project=None,
            job_id=f"gemini:{_SID}",
        ),
    ]
    out = collapse_gemini_sessions(rows)
    assert len(out) == 1
    s = out[0]
    assert (s.input_tokens, s.output_tokens, s.cache_read) == (59970, 1451, 170196)
    assert s.project == "kormilo/halyard"  # attributed row wins the tie


def test_multi_turn_hook_only_keeps_max() -> None:
    rows = [
        _gem(start=_T, end=_T + timedelta(minutes=1), inp=1000, out=10, cache=0, session_id=_SID),
        _gem(
            start=_T + timedelta(minutes=1),
            end=_T + timedelta(minutes=2),
            inp=3000,
            out=40,
            cache=0,
            session_id=_SID,
        ),
        _gem(
            start=_T + timedelta(minutes=2),
            end=_T + timedelta(minutes=3),
            inp=5000,
            out=70,
            cache=0,
            session_id=_SID,
        ),
    ]
    out = collapse_gemini_sessions(rows)
    assert len(out) == 1
    assert out[0].input_tokens == 5000 and out[0].output_tokens == 70


def test_distinct_sessions_not_merged() -> None:
    rows = [
        _gem(start=_T, end=_T + timedelta(minutes=1), inp=100, out=1, cache=0, session_id="aaa"),
        _gem(start=_T, end=_T + timedelta(minutes=1), inp=200, out=2, cache=0, session_id="bbb"),
    ]
    out = collapse_gemini_sessions(rows)
    assert {s.session_id for s in out} == {"aaa", "bbb"}
    assert len(out) == 2


def test_non_gemini_and_idless_rows_untouched() -> None:
    claude_a = AiSession(
        start=_T,
        end=_T + timedelta(minutes=1),
        tool="claude-code",
        model="claude",
        input_tokens=100,
        output_tokens=10,
        cost_usd=0.0,
        session_id="shared",  # same id, but different tool — must NOT collapse
    )
    claude_b = AiSession(
        start=_T + timedelta(minutes=1),
        end=_T + timedelta(minutes=2),
        tool="claude-code",
        model="claude",
        input_tokens=200,
        output_tokens=20,
        cost_usd=0.0,
        session_id="shared",
    )
    gem_no_id = _gem(start=_T, end=_T + timedelta(minutes=1), inp=50, out=5, cache=0)
    out = collapse_gemini_sessions([claude_a, claude_b, gem_no_id])
    assert len(out) == 3  # claude per-turn rows preserved; id-less gemini kept


def test_order_preserved_at_first_member_position() -> None:
    other = _gem(start=_T, end=_T + timedelta(minutes=1), inp=9, out=9, cache=0, session_id="zzz")
    a1 = _gem(start=_T, end=_T + timedelta(minutes=1), inp=1, out=1, cache=0, session_id="g")
    a2 = _gem(start=_T, end=_T + timedelta(minutes=2), inp=5, out=5, cache=0, session_id="g")
    out = collapse_gemini_sessions([a1, other, a2])
    # group "g" emits once at a1's position; "zzz" stays second.
    assert [s.session_id for s in out] == ["g", "zzz"]
    assert out[0].input_tokens == 5  # canonical (max) kept


def test_idempotent() -> None:
    rows = [
        _gem(start=_T, end=_T + timedelta(minutes=1), inp=1000, out=10, cache=0, session_id=_SID),
        _gem(
            start=_T + timedelta(minutes=1),
            end=_T + timedelta(minutes=2),
            inp=3000,
            out=40,
            cache=0,
            session_id=_SID,
        ),
    ]
    once = collapse_gemini_sessions(rows)
    twice = collapse_gemini_sessions(once)
    assert once == twice


def test_parse_sessions_applies_collapse(tmp_path: Path) -> None:
    """End-to-end: writing the three real rows to a log and reading it back
    surfaces one canonical session (the choke point all surfaces share)."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "halyard.toml").write_text('[project]\nslug = "kormilo/halyard"')
    (project_dir / AI_LOG_FILENAME).write_text("")
    for r in (
        _gem(
            start=_T,
            end=_T + timedelta(seconds=99),
            inp=27246,
            out=88,
            cache=24698,
            project="kormilo/halyard",
            session_id=_SID,
        ),
        _gem(
            start=_T + timedelta(seconds=99),
            end=_T + timedelta(seconds=709),
            inp=59970,
            out=1451,
            cache=170196,
            project="kormilo/halyard",
            session_id=_SID,
        ),
        _gem(
            start=_T,
            end=_T + timedelta(seconds=707),
            inp=59970,
            out=1451,
            cache=170196,
            job_id=f"gemini:{_SID}",
        ),
    ):
        append_session(project_dir, r)

    sessions = parse_sessions(project_dir, now=_T + timedelta(hours=1))
    gem = [s for s in sessions if s.tool == "gemini-cli"]
    assert len(gem) == 1
    assert gem[0].output_tokens == 1451
    assert sum(s.output_tokens for s in gem) == 1451  # no double-count
