"""Tests for v2.17 log integrity: locking primitive and amendment records.

Tasks covered:
    1.3  100 concurrent append_session calls → exactly 100 lines
    2.5  Round-trip an attribution change via an ``a`` record
    2.6  Multiple amendments on same session, last-write-wins per key
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime
from pathlib import Path

from halyard.ai_log import (
    AI_LOG_FILENAME,
    HEADER,
    AiSession,
    Amendment,
    append_session,
    locked_file,
    parse_amendment,
    parse_sessions,
    session_hash,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session(
    project: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> AiSession:
    start = start or datetime(2026, 1, 1, 9, 0, 0)
    end = end or datetime(2026, 1, 1, 9, 30, 0)
    return AiSession(
        start=start,
        end=end,
        tool="claude-code",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=0.01,
        project=project,
    )


def _init_project(tmp_path: Path) -> None:
    (tmp_path / "halyard.toml").write_text("[business]\n")
    (tmp_path / AI_LOG_FILENAME).write_text(HEADER)


# ---------------------------------------------------------------------------
# Task 1.3: 100 concurrent appenders produce exactly 100 lines
# ---------------------------------------------------------------------------


def test_100_concurrent_appenders_produce_exactly_100_lines(tmp_path: Path) -> None:
    """flock ensures no two writers interleave — every line lands intact."""
    _init_project(tmp_path)

    def _append(_: int) -> None:
        append_session(tmp_path, _session())

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(_append, range(100)))

    log_path = tmp_path / AI_LOG_FILENAME
    lines = [
        line for line in log_path.read_text().splitlines() if line.startswith("s ")
    ]
    assert len(lines) == 100, f"Expected 100 session lines, got {len(lines)}"


# ---------------------------------------------------------------------------
# locked_file smoke test — basic write
# ---------------------------------------------------------------------------


def test_locked_file_writes_content(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "test.log"
    with locked_file(path, "w") as f:
        f.write("hello\n")  # type: ignore[union-attr]
    assert path.read_text() == "hello\n"


def test_locked_file_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "c" / "test.log"
    with locked_file(path, "w") as f:
        f.write("ok\n")  # type: ignore[union-attr]
    assert path.exists()


# ---------------------------------------------------------------------------
# Task 2.1: session_hash
# ---------------------------------------------------------------------------


def test_session_hash_returns_12_hex_chars() -> None:
    line = "s 2026-01-01T09:00:00 2026-01-01T09:30:00 claude-code claude-sonnet-4-6 1000 200 0.0100"
    h = session_hash(line)
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


def test_session_hash_strips_whitespace() -> None:
    line = "s 2026-01-01T09:00:00 2026-01-01T09:30:00 claude-code claude-sonnet-4-6 1000 200 0.0100"
    assert session_hash(line) == session_hash(line + "  ")
    assert session_hash(line) == session_hash("  " + line)


# ---------------------------------------------------------------------------
# Task 2.2: parse_amendment
# ---------------------------------------------------------------------------


def test_parse_amendment_basic() -> None:
    line = "a abc123def456 project=acme:auth source=backfill"
    amendment = parse_amendment(line)
    assert amendment is not None
    assert amendment.session_hash == "abc123def456"
    assert amendment.kvs["project"] == "acme:auth"
    assert amendment.kvs["source"] == "backfill"


def test_parse_amendment_rejects_non_a_line() -> None:
    assert parse_amendment("s 2026-01-01T09:00:00 ...") is None


def test_parse_amendment_empty_kvs() -> None:
    amendment = parse_amendment("a abc123def456")
    assert amendment is not None
    assert amendment.kvs == {}


# ---------------------------------------------------------------------------
# Task 2.3: AiSession.apply_amendment
# ---------------------------------------------------------------------------


def test_apply_amendment_changes_project() -> None:
    session = _session(project="old:project")
    amendment = Amendment(session_hash="irrelevant", kvs={"project": "new:project"})
    session.apply_amendment(amendment)
    assert session.project == "new:project"


def test_apply_amendment_changes_source() -> None:
    session = _session()
    amendment = Amendment(session_hash="irrelevant", kvs={"source": "manual"})
    session.apply_amendment(amendment)
    assert session.source == "manual"


def test_apply_amendment_ignores_unknown_keys() -> None:
    session = _session(project="acme:auth")
    amendment = Amendment(session_hash="irrelevant", kvs={"future_field": "value"})
    session.apply_amendment(amendment)
    # No error raised; known fields unchanged
    assert session.project == "acme:auth"


# ---------------------------------------------------------------------------
# Task 2.5: Round-trip attribution change via ``a`` record
# ---------------------------------------------------------------------------


def test_round_trip_attribution_change_via_amendment(tmp_path: Path) -> None:
    """Write a session, append an ``a`` record, parse, assert project changed."""
    _init_project(tmp_path)
    log_path = tmp_path / AI_LOG_FILENAME

    # Write original session
    session = _session(project=None)
    append_session(tmp_path, session)

    # Compute the hash of the raw line just written
    raw_lines = [
        line for line in log_path.read_text().splitlines() if line.startswith("s ")
    ]
    assert len(raw_lines) == 1
    s_line = raw_lines[0]
    h = session_hash(s_line)

    # Append an amendment that attributes the session
    amendment_line = f"a {h} project=acme:auth source=manual\n"
    with log_path.open("a") as f:
        f.write(amendment_line)

    # Parse and verify the amendment was folded in
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].project == "acme:auth"
    assert sessions[0].source == "manual"


# ---------------------------------------------------------------------------
# Task 2.6: Multiple amendments, last-write-wins per key
# ---------------------------------------------------------------------------


def test_multiple_amendments_last_write_wins(tmp_path: Path) -> None:
    _init_project(tmp_path)
    log_path = tmp_path / AI_LOG_FILENAME

    # Write original session
    append_session(tmp_path, _session(project=None))

    raw_lines = [
        line for line in log_path.read_text().splitlines() if line.startswith("s ")
    ]
    h = session_hash(raw_lines[0])

    # First amendment: project=acme:auth
    with log_path.open("a") as f:
        f.write(f"a {h} project=acme:auth source=backfill\n")

    # Second amendment: project=acme:billing (should win on project key)
    # but source=backfill from the first amendment should still hold if not
    # overridden — but the second one sets source=manual which overrides it
    with log_path.open("a") as f:
        f.write(f"a {h} project=acme:billing source=manual\n")

    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 1
    # Last amendment wins on both keys
    assert sessions[0].project == "acme:billing"
    assert sessions[0].source == "manual"


def test_multiple_amendments_partial_key_override(tmp_path: Path) -> None:
    """Second amendment overrides only its own key; first amendment's other keys survive."""
    _init_project(tmp_path)
    log_path = tmp_path / AI_LOG_FILENAME

    append_session(tmp_path, _session(project=None))
    raw_lines = [
        line for line in log_path.read_text().splitlines() if line.startswith("s ")
    ]
    h = session_hash(raw_lines[0])

    # First amendment sets both project and source
    with log_path.open("a") as f:
        f.write(f"a {h} project=acme:auth source=backfill\n")

    # Second amendment overrides only project; source from first still applies
    # (apply_amendment is called in order, later calls overwrite same key)
    with log_path.open("a") as f:
        f.write(f"a {h} project=acme:billing\n")

    sessions = parse_sessions(tmp_path)
    assert sessions[0].project == "acme:billing"
    assert sessions[0].source == "backfill"  # not overridden by second amendment


# ---------------------------------------------------------------------------
# Backwards compat: pure-s-line logs still parse correctly
# ---------------------------------------------------------------------------


def test_pure_s_line_log_parses_without_amendments(tmp_path: Path) -> None:
    _init_project(tmp_path)
    append_session(tmp_path, _session(project="acme:auth"))
    append_session(tmp_path, _session(project="acme:dash"))
    sessions = parse_sessions(tmp_path)
    assert len(sessions) == 2
    assert {s.project for s in sessions} == {"acme:auth", "acme:dash"}
