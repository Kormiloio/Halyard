"""Tests for v2.24 outcome metadata: AiSession fields, serialization, tag migration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from halyard.ai_log import (
    AI_LOG_FILENAME,
    HEADER,
    AiSession,
    parse_amendment,
    parse_sessions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_START = datetime(2026, 5, 1, 10, 0)
_END = datetime(2026, 5, 1, 11, 0)


_BASE = "s 2026-05-01T10:00:00 2026-05-01T11:00:00 claude-code claude-sonnet-4-6 100 50 0.0100"


def _session(**kwargs) -> AiSession:  # type: ignore[no-untyped-def]
    defaults: dict = {
        "start": _START,
        "end": _END,
        "tool": "claude-code",
        "model": "claude-sonnet-4-6",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": 0.01,
    }
    defaults.update(kwargs)
    return AiSession(**defaults)


def _write_log(tmp_path: Path, lines: list[str]) -> Path:
    log = tmp_path / AI_LOG_FILENAME
    log.write_text(HEADER + "\n".join(lines) + "\n")
    return tmp_path


# ---------------------------------------------------------------------------
# AiSession new fields default to None
# ---------------------------------------------------------------------------


def test_new_fields_default_none() -> None:
    s = _session()
    assert s.branch is None
    assert s.commit_count is None
    assert s.pr_ref is None
    assert s.pr_state is None
    assert s.outcome_resolved_at is None


# ---------------------------------------------------------------------------
# Serialization — to_log_line
# ---------------------------------------------------------------------------


def test_branch_serialized() -> None:
    s = _session(branch="feature/auth")
    line = s.to_log_line()
    assert "branch=feature/auth" in line


def test_commit_count_serialized() -> None:
    s = _session(commit_count=3)
    line = s.to_log_line()
    assert "commit_count=3" in line


def test_pr_ref_serialized() -> None:
    s = _session(pr_ref="owner/repo#42")
    line = s.to_log_line()
    assert "pr_ref=owner/repo#42" in line


def test_pr_state_serialized() -> None:
    s = _session(pr_state="merged")
    line = s.to_log_line()
    assert "pr_state=merged" in line


def test_outcome_resolved_at_serialized() -> None:
    s = _session(outcome_resolved_at="2026-05-01T12:00:00")
    line = s.to_log_line()
    assert "outcome_resolved_at=2026-05-01T12:00:00" in line


def test_none_fields_not_serialized() -> None:
    s = _session()
    line = s.to_log_line()
    assert "branch=" not in line
    assert "commit_count=" not in line
    assert "pr_ref=" not in line
    assert "pr_state=" not in line
    assert "outcome_resolved_at=" not in line


def test_zero_commit_count_serialized() -> None:
    s = _session(commit_count=0)
    line = s.to_log_line()
    assert "commit_count=0" in line


# ---------------------------------------------------------------------------
# Parsing — KV dispatch
# ---------------------------------------------------------------------------


def test_parse_branch_field(tmp_path: Path) -> None:
    s = _session(branch="main")
    _write_log(tmp_path, [s.to_log_line()])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].branch == "main"


def test_parse_commit_count(tmp_path: Path) -> None:
    s = _session(commit_count=7)
    _write_log(tmp_path, [s.to_log_line()])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].commit_count == 7


def test_parse_pr_ref_and_state(tmp_path: Path) -> None:
    s = _session(pr_ref="Kormilo/Halyard#99", pr_state="merged")
    _write_log(tmp_path, [s.to_log_line()])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].pr_ref == "Kormilo/Halyard#99"
    assert sessions[0].pr_state == "merged"


def test_parse_outcome_resolved_at(tmp_path: Path) -> None:
    s = _session(outcome_resolved_at="2026-05-01T15:30:00")
    _write_log(tmp_path, [s.to_log_line()])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].outcome_resolved_at == "2026-05-01T15:30:00"


def test_parse_unknown_outcome_keys_ignored(tmp_path: Path) -> None:
    _write_log(tmp_path, [f"{_BASE} future_key=xyz"])
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1  # not quarantined


# ---------------------------------------------------------------------------
# Tag migration: legacy "branch:<name>" → branch field
# ---------------------------------------------------------------------------


def test_legacy_branch_tag_promoted_to_field(tmp_path: Path) -> None:
    _write_log(tmp_path, [f"{_BASE} tags=branch:main"])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].branch == "main"


def test_legacy_branch_tag_not_promoted_when_branch_field_present(tmp_path: Path) -> None:
    _write_log(tmp_path, [f"{_BASE} branch=feature/x tags=branch:main"])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].branch == "feature/x"  # explicit field wins


def test_non_branch_tags_not_promoted(tmp_path: Path) -> None:
    _write_log(tmp_path, [f"{_BASE} tags=attribution:inferred"])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].branch is None


def test_mixed_tags_only_branch_promoted(tmp_path: Path) -> None:
    _write_log(tmp_path, [f"{_BASE} tags=branch:dev,attribution:inferred"])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].branch == "dev"
    assert "attribution:inferred" in sessions[0].tags


# ---------------------------------------------------------------------------
# Amendment folding for pr_ref and pr_state
# ---------------------------------------------------------------------------


def test_amendment_sets_pr_ref(tmp_path: Path) -> None:
    s = _session()
    line = s.to_log_line()
    from halyard.ai_log import session_hash

    h = session_hash(line)
    amendment_line = f"a {h} pr_ref=owner/repo#5 pr_state=merged"
    _write_log(tmp_path, [line, amendment_line])
    sessions = parse_sessions(tmp_path)
    assert sessions[0].pr_ref == "owner/repo#5"
    assert sessions[0].pr_state == "merged"


def test_amendment_last_write_wins_pr_state(tmp_path: Path) -> None:
    s = _session()
    line = s.to_log_line()
    from halyard.ai_log import session_hash

    h = session_hash(line)
    _write_log(
        tmp_path,
        [
            line,
            f"a {h} pr_state=open",
            f"a {h} pr_state=merged",
        ],
    )
    sessions = parse_sessions(tmp_path)
    assert sessions[0].pr_state == "merged"


def test_parse_amendment_allows_pr_keys() -> None:
    line = "a abc123def456 pr_ref=owner/repo#7 pr_state=closed"
    amendment = parse_amendment(line)
    assert amendment is not None
    assert amendment.kvs["pr_ref"] == "owner/repo#7"
    assert amendment.kvs["pr_state"] == "closed"


# ---------------------------------------------------------------------------
# Round-trip: all new fields survive serialize → parse
# ---------------------------------------------------------------------------


def test_full_round_trip(tmp_path: Path) -> None:
    s = _session(
        branch="feature/outcome",
        commit_count=4,
        pr_ref="Kormilo/Halyard#42",
        pr_state="merged",
        outcome_resolved_at="2026-05-01T12:00:00",
    )
    _write_log(tmp_path, [s.to_log_line()])
    parsed = parse_sessions(tmp_path)[0]
    assert parsed.branch == "feature/outcome"
    assert parsed.commit_count == 4
    assert parsed.pr_ref == "Kormilo/Halyard#42"
    assert parsed.pr_state == "merged"
    assert parsed.outcome_resolved_at == "2026-05-01T12:00:00"
