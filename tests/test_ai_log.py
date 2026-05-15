"""Tests for ai_log.py — AiSession serialization, parsing, and project discovery."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from halyard.ai_log import (
    AI_LOG_FILENAME,
    HEADER,
    AiSession,
    _safe_field,
    append_session,
    assign_unattributed_sessions,
    backfill_window,
    find_project_dir,
    parse_sessions,
    read_active_project,
    write_unattributed_session,
)

START = datetime(2026, 5, 6, 10, 30, 0)
END = datetime(2026, 5, 6, 11, 15, 0)


def _session(**kwargs) -> AiSession:  # type: ignore[no-untyped-def]
    defaults = {
        "start": START,
        "end": END,
        "tool": "claude-code",
        "model": "claude-sonnet-4-6",
        "input_tokens": 10000,
        "output_tokens": 2000,
        "cost_usd": 0.0600,
    }
    defaults.update(kwargs)
    return AiSession(**defaults)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_to_log_line_positional_fields() -> None:
    line = _session().to_log_line()
    parts = line.split()
    assert parts[0] == "s"
    assert parts[1] == "2026-05-06T10:30:00"
    assert parts[2] == "2026-05-06T11:15:00"
    assert parts[3] == "claude-code"
    assert parts[4] == "claude-sonnet-4-6"
    assert parts[5] == "10000"
    assert parts[6] == "2000"
    assert parts[7] == "0.0600"


def test_to_log_line_cost_four_decimal_places() -> None:
    line = _session(cost_usd=1.5).to_log_line()
    assert "1.5000" in line


def test_to_log_line_optional_project() -> None:
    line = _session(project="acme:auth-migration").to_log_line()
    assert "project=acme:auth-migration" in line


def test_to_log_line_omits_default_billing() -> None:
    line = _session(billing="api").to_log_line()
    assert "billing=" not in line


def test_to_log_line_includes_non_default_billing() -> None:
    line = _session(billing="seat").to_log_line()
    assert "billing=seat" in line


def test_to_log_line_tokens_available_false() -> None:
    line = _session(tokens_available=False).to_log_line()
    assert "tokens_available=false" in line


def test_to_log_line_omits_tokens_available_when_true() -> None:
    line = _session(tokens_available=True).to_log_line()
    assert "tokens_available" not in line


def test_to_log_line_note_spaces_become_underscores() -> None:
    line = _session(note="quick check").to_log_line()
    assert "note=quick_check" in line


def test_to_log_line_tags() -> None:
    line = _session(tags=["review", "refactor"]).to_log_line()
    assert "tags=review,refactor" in line


def test_to_log_line_cache_fields() -> None:
    line = _session(cache_read=5000, cache_write=1000).to_log_line()
    assert "cache_read=5000" in line
    assert "cache_write=1000" in line


def test_to_log_line_job_id_and_source() -> None:
    line = _session(job_id="droid-001", source="hook").to_log_line()
    assert "job_id=droid-001" in line
    assert "source=hook" in line


# ---------------------------------------------------------------------------
# Round-trip: write → parse
# ---------------------------------------------------------------------------


def test_round_trip_minimal(tmp_path: Path) -> None:
    s = _session()
    append_session(tmp_path, s)
    parsed = parse_sessions(tmp_path)
    assert len(parsed) == 1
    p = parsed[0]
    assert p.start == s.start
    assert p.end == s.end
    assert p.tool == s.tool
    assert p.model == s.model
    assert p.input_tokens == s.input_tokens
    assert p.output_tokens == s.output_tokens
    assert abs(p.cost_usd - s.cost_usd) < 0.0001


def test_round_trip_all_optional_fields(tmp_path: Path) -> None:
    s = _session(
        project="acme:auth",
        user="mario",
        cache_read=3000,
        cache_write=500,
        tokens_available=False,
        billing="credits",
        credits=12.5,
        job_id="job-abc",
        source="proxy",
        tags=["refactor"],
        note="big refactor",
    )
    append_session(tmp_path, s)
    p = parse_sessions(tmp_path)[0]
    assert p.project == "acme:auth"
    assert p.user == "mario"
    assert p.cache_read == 3000
    assert p.cache_write == 500
    assert p.tokens_available is False
    assert p.billing == "credits"
    assert p.credits == pytest.approx(12.5)
    assert p.job_id == "job-abc"
    assert p.source == "proxy"
    assert p.tags == ["refactor"]
    assert p.note == "big refactor"


def test_parse_ignores_comments_and_blanks(tmp_path: Path) -> None:
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(HEADER + "\n\n; a comment\n")
    assert parse_sessions(tmp_path) == []


def test_parse_ignores_unknown_kv(tmp_path: Path) -> None:
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(
        HEADER + "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-opus-4-7 "
        "5000 1000 0.8250 future_field=xyz\n"
    )
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1


def test_from_log_line_negative_tokens_quarantines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    line = "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-opus-4-7 -1 1000 0.8250"

    assert AiSession.from_log_line(line) is None

    quarantine = tmp_path / ".halyard" / "quarantine.log"
    assert quarantine.exists()
    assert "input_tokens" in quarantine.read_text()


def test_from_log_line_missing_required_field_quarantines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    line = "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code"

    assert AiSession.from_log_line(line) is None

    quarantine = tmp_path / ".halyard" / "quarantine.log"
    assert quarantine.exists()
    assert "expected session line" in quarantine.read_text()


def test_from_log_line_bad_cost_quarantines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    line = "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-opus-4-7 100 50 nope"

    assert AiSession.from_log_line(line) is None

    quarantine = tmp_path / ".halyard" / "quarantine.log"
    assert quarantine.exists()
    assert "invalid cost_usd: nope" in quarantine.read_text()


def test_log_line_error_does_not_write_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    line = "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-opus-4-7 100 bad 0.1234"

    assert AiSession.log_line_error(line) == "invalid output_tokens: bad"
    assert not (tmp_path / ".halyard" / "quarantine.log").exists()


def test_write_unattributed_session_creates_user_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    path = write_unattributed_session(_session(tool="codex"))

    assert path == tmp_path / ".halyard" / "unattributed.log"
    assert "tool" not in path.read_text()
    assert "codex" in path.read_text()


def test_assign_unattributed_sessions_adds_project(tmp_path: Path) -> None:
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(
        HEADER + "s 2026-05-06T10:00:00 2026-05-06T10:30:00 codex codex-local "
        "5000 1000 0.0000 source=codex\n"
    )

    changed = assign_unattributed_sessions(tmp_path, "acme:auth")

    assert changed == 1
    session = parse_sessions(tmp_path)[0]
    assert session.project == "acme:auth"
    assert session.source == "codex"


def test_assign_unattributed_sessions_skips_attributed_records(tmp_path: Path) -> None:
    append_session(tmp_path, _session(project="acme:auth"))

    changed = assign_unattributed_sessions(tmp_path, "globex:reports")

    assert changed == 0
    assert parse_sessions(tmp_path)[0].project == "acme:auth"


def test_append_multiple_sessions(tmp_path: Path) -> None:
    for i in range(3):
        append_session(tmp_path, _session(input_tokens=i * 1000))
    assert len(parse_sessions(tmp_path)) == 3


# ---------------------------------------------------------------------------
# Project discovery
# ---------------------------------------------------------------------------


def test_find_project_dir_finds_halyard_toml(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    assert find_project_dir(tmp_path) == tmp_path


def test_find_project_dir_walks_up(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    subdir = tmp_path / "src" / "deep"
    subdir.mkdir(parents=True)
    assert find_project_dir(subdir) == tmp_path


def test_find_project_dir_returns_none_when_absent(tmp_path: Path) -> None:
    assert find_project_dir(tmp_path) is None


# ---------------------------------------------------------------------------
# Rich session telemetry (v2.6)
# ---------------------------------------------------------------------------


def _base_session(**kwargs) -> AiSession:  # type: ignore[no-untyped-def]
    return AiSession(
        start=datetime(2026, 5, 8, 10, 0, 0),
        end=datetime(2026, 5, 8, 10, 30, 0),
        tool="gemini-cli",
        model="gemini-2.0-flash",
        input_tokens=500,
        output_tokens=200,
        cost_usd=0.0012,
        **kwargs,
    )


def test_rich_fields_round_trip() -> None:
    session = _base_session(
        session_id="abc123def456",
        tool_calls=42,
        tool_errors=3,
        wall_seconds=1800,
        agent_active_seconds=900,
        code_added=150,
        code_removed=40,
        model_breakdown="gemini-2.0-flash:8|gemini-2.0-pro:2",
    )
    line = session.to_log_line()
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.session_id == "abc123def456"
    assert parsed.tool_calls == 42
    assert parsed.tool_errors == 3
    assert parsed.wall_seconds == 1800
    assert parsed.agent_active_seconds == 900
    assert parsed.code_added == 150
    assert parsed.code_removed == 40
    assert parsed.model_breakdown == "gemini-2.0-flash:8|gemini-2.0-pro:2"


def test_rich_fields_absent_on_old_log_line() -> None:
    line = "s 2026-05-08T10:00:00 2026-05-08T10:30:00 gemini-cli gemini-2.0-flash 500 200 0.0012"
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.tool_calls is None
    assert parsed.tool_errors is None
    assert parsed.wall_seconds is None
    assert parsed.session_id is None
    assert parsed.model_breakdown is None


def test_rich_fields_omitted_when_none() -> None:
    session = _base_session()
    line = session.to_log_line()
    assert "tool_calls" not in line
    assert "tool_errors" not in line
    assert "wall_seconds" not in line
    assert "session_id" not in line
    assert "model_breakdown" not in line


def test_malformed_rich_field_ignored() -> None:
    line = (
        "s 2026-05-08T10:00:00 2026-05-08T10:30:00 gemini-cli gemini-2.0-flash"
        " 500 200 0.0012 tool_calls=notanint"
    )
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.tool_calls is None


def test_unknown_rich_field_ignored() -> None:
    line = (
        "s 2026-05-08T10:00:00 2026-05-08T10:30:00 gemini-cli gemini-2.0-flash"
        " 500 200 0.0012 future_field=somevalue"
    )
    parsed = AiSession.from_log_line(line)
    assert parsed is not None  # must not crash


def test_tool_errors_zero_written_when_calls_known() -> None:
    # tool_errors=0 is meaningful: "5 calls, 0 errors" vs "unknown"
    session = _base_session(tool_calls=5, tool_errors=0)
    line = session.to_log_line()
    assert "tool_calls=5" in line
    assert "tool_errors=0" in line


# ---------------------------------------------------------------------------
# M-1: Newline injection sanitization in tool/model fields
# ---------------------------------------------------------------------------


def test_safe_field_strips_newline() -> None:
    assert "\n" not in _safe_field("cursor\nmalicious")


def test_safe_field_strips_equals() -> None:
    assert "=" not in _safe_field("model=evil")


def test_safe_field_strips_tab_and_spaces() -> None:
    result = _safe_field("bad\tfield value")
    assert "\t" not in result
    assert " " not in result


def test_safe_field_caps_at_128_chars() -> None:
    assert len(_safe_field("x" * 200)) == 128


def test_newline_injection_tool_sanitized(tmp_path: Path) -> None:
    """A tool value with an embedded newline must not corrupt the log."""
    s = _session(tool="cursor\ncost_usd=0.0000 project=evil:client")
    append_session(tmp_path, s)

    raw = (tmp_path / AI_LOG_FILENAME).read_text()
    # The injected newline must not create extra lines in the log
    data_lines = [ln for ln in raw.splitlines() if ln.startswith("s ")]
    assert len(data_lines) == 1, "Newline injection created extra log lines"


def test_newline_injection_model_sanitized(tmp_path: Path) -> None:
    """A model value with an embedded newline must not corrupt the log."""
    s = _session(model="bad model\n s 2026-01-01T00:00:00 2026-01-01T01:00:00 fake fake 0 0 0.0")
    append_session(tmp_path, s)

    raw = (tmp_path / AI_LOG_FILENAME).read_text()
    data_lines = [ln for ln in raw.splitlines() if ln.startswith("s ")]
    assert len(data_lines) == 1, "Newline injection created extra log lines"


def test_newline_injection_round_trips_safely(tmp_path: Path) -> None:
    """After sanitization, the log line must still parse to a valid session."""
    s = _session(tool="cursor\nevil", model="gpt-4o\nevil")
    append_session(tmp_path, s)
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    # Newlines replaced with underscores, so field contains no whitespace
    assert "\n" not in sessions[0].tool
    assert "\n" not in sessions[0].model


@pytest.mark.parametrize(
    "field,payload",
    [
        ("project", "good:slug cost_usd=0 project=evil"),
        ("user", "alice billing=free"),
        ("billing", "credits\nstatus=hacked"),
        ("job_id", "abc def=ghi"),
        ("source", "hook source=spoof"),
        ("attr_method", "git\tnewline"),
        ("branch", "feat/x project=evil"),
        ("pr_ref", "owner/repo#1 tags=evil"),
        ("pr_state", "open pr_state=closed"),
        ("outcome_resolved_at", "2026-01-01 outcome=hacked"),
        ("session_id", "id with spaces=bad"),
        ("model_breakdown", "gpt:1 fake=field"),
    ],
)
def test_metadata_injection_sanitized(tmp_path: Path, field: str, payload: str) -> None:
    """Whitespace/= injection in any string metadata field must not corrupt the log."""
    s = _session(**{field: payload})
    append_session(tmp_path, s)
    raw = (tmp_path / AI_LOG_FILENAME).read_text()
    data_lines = [ln for ln in raw.splitlines() if ln.startswith("s ")]
    assert len(data_lines) == 1
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1


def test_tags_injection_sanitized(tmp_path: Path) -> None:
    """A tag containing space/= must not break the log."""
    s = _session(tags=["normal", "bad tag=evil"])
    append_session(tmp_path, s)
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1


# ---------------------------------------------------------------------------
# M-2: note/resume_command encoding documentation (round-trip verification)
# ---------------------------------------------------------------------------


def test_note_with_spaces_round_trips(tmp_path: Path) -> None:
    """Spaces in note are encoded as underscores and decoded back."""
    s = _session(note="quick check here")
    append_session(tmp_path, s)
    parsed = parse_sessions(tmp_path)[0]
    assert parsed.note == "quick check here"


def test_note_with_underscores_ambiguity_documented(tmp_path: Path) -> None:
    """Literal underscores in note are indistinguishable from encoded spaces after round-trip.
    This test documents the known limitation described in M-2."""
    s = _session(note="snake_case_note")
    line = s.to_log_line()
    # Underscores are preserved as-is in the encoded form
    assert "note=snake_case_note" in line
    # After decoding, underscores become spaces — this is the documented ambiguity
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.note == "snake case note"  # underscores decoded as spaces


def test_resume_command_with_spaces_round_trips(tmp_path: Path) -> None:
    """Spaces in resume_command are encoded as underscores and decoded back."""
    s = _session(resume_command="gemini --resume session-123")
    append_session(tmp_path, s)
    parsed = parse_sessions(tmp_path)[0]
    assert parsed.resume_command == "gemini --resume session-123"


def test_note_newline_stripped_on_encode(tmp_path: Path) -> None:
    """Newlines in note are stripped/replaced before writing to log."""
    s = _session(note="line one\nline two")
    line = s.to_log_line()
    assert "\n" not in line


# ---------------------------------------------------------------------------
# M-5: Quarantine error string escaping
# ---------------------------------------------------------------------------


def test_quarantine_error_newline_escaped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Embedded newlines in the error string must not inject extra '; error=' header lines.

    The _write_quarantine function receives error strings derived from user-controlled
    field values (e.g. 'invalid start timestamp: <value>').  If that value contained
    a newline it would produce a second '; error=' line, confusing quarantine readers.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Directly exercise _write_quarantine with an error string that contains a newline
    from halyard.ai_log import _write_quarantine

    _write_quarantine(
        "s 2026-05-06T10:00:00 2026-05-06T11:00:00 tool model 0 0 0.0",
        "invalid start timestamp: bad\n; error=injected",
    )

    quarantine = tmp_path / ".halyard" / "quarantine.log"
    assert quarantine.exists()
    content = quarantine.read_text()
    # Must have exactly one "; error=" line — the injected one must be stripped
    error_lines = [ln for ln in content.splitlines() if ln.startswith("; error=")]
    assert len(error_lines) == 1, f"Injected extra error header lines:\n{content!r}"
    # The injected fragment must not appear as a standalone header line
    assert "; error=injected" not in content or "invalid start timestamp" in error_lines[0]


def test_quarantine_error_no_carriage_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Carriage returns in error strings are also stripped."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from halyard.ai_log import _write_quarantine

    _write_quarantine(
        "s bad-line",
        "invalid field: value\r; error=cr-injected",
    )

    quarantine = tmp_path / ".halyard" / "quarantine.log"
    content = quarantine.read_text()
    assert "\r" not in content
    error_lines = [ln for ln in content.splitlines() if ln.startswith("; error=")]
    assert len(error_lines) == 1


# ---------------------------------------------------------------------------
# L-3: assign_unattributed_sessions uses atomic write (tmp → replace)
# ---------------------------------------------------------------------------


def test_assign_unattributed_sessions_atomic_write(tmp_path: Path) -> None:
    """assign_unattributed_sessions must write via a temp file then rename."""
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(
        HEADER + "s 2026-05-06T10:00:00 2026-05-06T10:30:00 codex codex-local "
        "5000 1000 0.0000 source=codex\n"
    )

    tmp_file = log.with_suffix(".log.tmp")
    # Confirm no stale tmp exists before the call
    assert not tmp_file.exists()

    changed = assign_unattributed_sessions(tmp_path, "acme:auth")

    # After successful write the tmp file must have been renamed away
    assert changed == 1
    assert not tmp_file.exists()
    assert log.exists()
    sessions = parse_sessions(tmp_path)
    assert sessions[0].project == "acme:auth"


def test_assign_unattributed_no_change_leaves_no_tmp(tmp_path: Path) -> None:
    """If nothing changes, no tmp file should be created."""
    append_session(tmp_path, _session(project="acme:auth"))

    changed = assign_unattributed_sessions(tmp_path, "other:proj")

    assert changed == 0
    assert not (tmp_path / AI_LOG_FILENAME).with_suffix(".log.tmp").exists()


# ---------------------------------------------------------------------------
# D-1: Attribution provenance — attr_method field and attribution:inferred tag
# ---------------------------------------------------------------------------


def test_attr_method_timer_round_trips() -> None:
    """attr_method=timer survives a log write/read cycle."""
    s = _session(project="acme:auth", attr_method="timer")
    line = s.to_log_line()
    assert "attr_method=timer" in line
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.attr_method == "timer"


def test_attr_method_git_round_trips() -> None:
    """attr_method=git survives a log write/read cycle."""
    s = _session(project="acme:auth", attr_method="git")
    line = s.to_log_line()
    assert "attr_method=git" in line
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.attr_method == "git"


def test_attr_method_none_omitted_from_log_line() -> None:
    """When attr_method is None the field must not appear in the log line."""
    s = _session(project="acme:auth")
    assert s.attr_method is None
    assert "attr_method=" not in s.to_log_line()


def test_attr_method_backfill_set_by_assign_unattributed(tmp_path: Path) -> None:
    """assign_unattributed_sessions must write attr_method=backfill on every attributed line."""
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(
        HEADER + "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-sonnet-4-6 "
        "5000 1000 0.0500 source=hook\n"
    )

    assign_unattributed_sessions(tmp_path, "acme:auth")

    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].project == "acme:auth"
    assert sessions[0].attr_method == "backfill"


def test_attr_method_backfill_set_by_backfill_window(tmp_path: Path) -> None:
    """backfill_window must write attr_method=backfill on every attributed line."""
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(
        HEADER + "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-sonnet-4-6 "
        "5000 1000 0.0500 source=hook\n"
    )

    backfill_window(
        tmp_path,
        start=datetime(2026, 5, 6, 9, 0),
        end=datetime(2026, 5, 6, 11, 0),
        project="acme:auth",
    )

    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].project == "acme:auth"
    assert sessions[0].attr_method == "backfill"


def test_already_attributed_line_not_modified_by_assign(tmp_path: Path) -> None:
    """Lines that already have project= must not be touched by assign_unattributed_sessions."""
    s = _session(project="acme:auth", attr_method="timer")
    append_session(tmp_path, s)

    changed = assign_unattributed_sessions(tmp_path, "other:proj")

    assert changed == 0
    sessions = parse_sessions(tmp_path)
    assert sessions[0].project == "acme:auth"
    assert sessions[0].attr_method == "timer"  # original provenance preserved


def test_old_log_line_without_attr_method_parses_as_none() -> None:
    """Pre-D-1 log lines with no attr_method= field must parse with attr_method=None."""
    line = (
        "s 2026-05-06T10:00:00 2026-05-06T10:30:00 claude-code claude-sonnet-4-6 "
        "5000 1000 0.0500 project=acme:auth source=hook"
    )
    parsed = AiSession.from_log_line(line)
    assert parsed is not None
    assert parsed.attr_method is None  # backward-compatible: field absent → None


# ---------------------------------------------------------------------------
# D-2: Shared read_active_project() utility
# ---------------------------------------------------------------------------


def test_read_active_project_returns_slug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """read_active_project reads the slug= line from ~/.halyard/active."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text("timeclock=/some/path\nslug=acme:auth\nstarted=2026-05-06 10:00:00\n")

    assert read_active_project() == "acme:auth"


def test_read_active_project_returns_none_when_file_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """read_active_project returns None when ~/.halyard/active does not exist."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # no active file created
    assert read_active_project() is None


def test_read_active_project_returns_none_when_no_slug_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """read_active_project returns None when active file has no slug= line."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text("timeclock=/some/path\nstarted=2026-05-06 10:00:00\n")

    assert read_active_project() is None


def test_read_active_project_handles_partial_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """read_active_project returns None gracefully when file content is empty (partial write)."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    active = tmp_path / ".halyard" / "active"
    active.parent.mkdir(parents=True, exist_ok=True)
    active.write_text("")  # simulates truncated write before rename completes

    assert read_active_project() is None
