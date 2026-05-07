"""Tests for ai_log.py — AiSession serialization, parsing, and project discovery."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from halyard.ai_log import (
    AI_LOG_FILENAME,
    HEADER,
    AiSession,
    append_session,
    find_project_dir,
    parse_sessions,
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
