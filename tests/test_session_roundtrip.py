"""Gap 1: Session round-trip fidelity — write → parse → assert all fields identical.

Every field on AiSession must survive a to_log_line() / from_log_line() cycle
without loss (within documented encoding constraints).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from halyard.ai_log import AiSession

START = datetime(2026, 5, 8, 9, 0, 0)
END = datetime(2026, 5, 8, 10, 30, 0)


def _make(**kwargs) -> AiSession:  # type: ignore[no-untyped-def]
    defaults = {
        "start": START,
        "end": END,
        "tool": "claude-code",
        "model": "claude-sonnet-4-6",
        "input_tokens": 12000,
        "output_tokens": 3000,
        "cost_usd": 0.0810,
    }
    defaults.update(kwargs)
    return AiSession(**defaults)


def _rt(session: AiSession) -> AiSession:
    """Round-trip helper: serialise then parse."""
    line = session.to_log_line()
    result = AiSession.from_log_line(line)
    assert result is not None, f"from_log_line returned None for: {line!r}"
    return result


# ---------------------------------------------------------------------------
# Gap 1: Session round-trip fidelity
# ---------------------------------------------------------------------------


def test_session_roundtrip_all_fields() -> None:
    """All non-ambiguous fields survive a full log round-trip unchanged."""
    s = _make(
        project="acme:auth",
        user="mario@acme.com",
        cache_read=5000,
        cache_write=1000,
        tokens_available=False,
        billing="credits",
        credits=14.75,
        job_id="job-xyz-001",
        source="hook",
        attr_method="timer",
        tags=["review", "refactor"],
        session_id="abc123def456",
        tool_calls=7,
        tool_errors=1,
        wall_seconds=3600,
        agent_active_seconds=1800,
        code_added=200,
        code_removed=50,
        model_breakdown="claude-sonnet-4-6:3|claude-haiku-4-5:2",
    )
    p = _rt(s)

    assert p.start == s.start
    assert p.end == s.end
    assert p.tool == s.tool
    assert p.model == s.model
    assert p.input_tokens == s.input_tokens
    assert p.output_tokens == s.output_tokens
    assert p.cost_usd == pytest.approx(s.cost_usd, abs=1e-4)
    assert p.project == s.project
    assert p.user == s.user
    assert p.cache_read == s.cache_read
    assert p.cache_write == s.cache_write
    assert p.tokens_available == s.tokens_available
    assert p.billing == s.billing
    assert p.credits == pytest.approx(s.credits, abs=1e-4)  # type: ignore[arg-type]
    assert p.job_id == s.job_id
    assert p.source == s.source
    assert p.attr_method == s.attr_method
    assert p.tags == s.tags
    assert p.session_id == s.session_id
    assert p.tool_calls == s.tool_calls
    assert p.tool_errors == s.tool_errors
    assert p.wall_seconds == s.wall_seconds
    assert p.agent_active_seconds == s.agent_active_seconds
    assert p.code_added == s.code_added
    assert p.code_removed == s.code_removed
    assert p.model_breakdown == s.model_breakdown


def test_session_roundtrip_optional_fields_none() -> None:
    """None optional fields must not appear in the log line and parse back as None."""
    s = _make()
    line = s.to_log_line()

    # Verify none of the optional keys appear
    for key in (
        "project",
        "user",
        "cache_read",
        "cache_write",
        "billing",
        "credits",
        "job_id",
        "source",
        "attr_method",
        "tags",
        "note",
        "session_id",
        "tool_calls",
        "tool_errors",
        "wall_seconds",
        "agent_active_seconds",
        "code_added",
        "code_removed",
        "model_breakdown",
        "resume_command",
    ):
        assert f"{key}=" not in line, f"unexpected field in line: {key}={line}"

    p = _rt(s)
    assert p.project is None
    assert p.user is None
    assert p.cache_read is None
    assert p.cache_write is None
    assert p.billing == "api"
    assert p.credits is None
    assert p.job_id is None
    assert p.source is None
    assert p.attr_method is None
    assert p.tags == []
    assert p.note is None
    assert p.session_id is None
    assert p.tool_calls is None
    assert p.tool_errors is None
    assert p.wall_seconds is None
    assert p.agent_active_seconds is None
    assert p.code_added is None
    assert p.code_removed is None
    assert p.model_breakdown is None
    assert p.resume_command is None


def test_session_roundtrip_note_with_spaces() -> None:
    """Notes with spaces round-trip correctly (spaces ↔ underscores encoding)."""
    s = _make(note="reviewed auth module")
    p = _rt(s)
    assert p.note == "reviewed auth module"


def test_session_roundtrip_resume_command() -> None:
    """resume_command with spaces round-trips correctly."""
    s = _make(resume_command="gemini --resume abc123")
    p = _rt(s)
    assert p.resume_command == "gemini --resume abc123"


def test_session_roundtrip_zero_tool_errors_preserved() -> None:
    """tool_errors=0 is a meaningful value and must round-trip as 0, not None."""
    s = _make(tool_calls=5, tool_errors=0)
    p = _rt(s)
    assert p.tool_calls == 5
    assert p.tool_errors == 0
