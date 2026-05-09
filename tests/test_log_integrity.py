"""Tests for v2.17 log integrity: locking primitive and amendment records.

Tasks covered:
    1.3 / 7.1  100 concurrent append_session calls → exactly 100 lines
    2.5        Round-trip an attribution change via an ``a`` record
    2.6        Multiple amendments on same session, last-write-wins per key
    7.2        50 concurrent start_timer calls → 49 raise TimerAlreadyRunning
    7.3        CLI stop + dashboard stop simultaneously → exactly one ``o`` line
    7.4        Concurrent invoice allocation → unique numbers (no duplicates)
    7.5        Concurrent backfill_window + append_session → append survives
    6.4        Malformed log line in backfill → warning printed + log entry
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime
from pathlib import Path

import pytest

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
    lines = [line for line in log_path.read_text().splitlines() if line.startswith("s ")]
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
    raw_lines = [line for line in log_path.read_text().splitlines() if line.startswith("s ")]
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

    raw_lines = [line for line in log_path.read_text().splitlines() if line.startswith("s ")]
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
    raw_lines = [line for line in log_path.read_text().splitlines() if line.startswith("s ")]
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


# ---------------------------------------------------------------------------
# Task 7.1: already covered by test_100_concurrent_appenders_produce_exactly_100_lines
# (task 1.3 above). Marked done in tasks.md.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 7.2: 50 concurrent start_timer → 49 raise TimerAlreadyRunning
# ---------------------------------------------------------------------------


def test_50_concurrent_start_timer_exactly_one_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the first caller to acquire the timeclock flock can start the timer;
    all other concurrent callers must raise TimerAlreadyRunning.
    """
    from halyard.orchestration import TimerAlreadyRunning, start_timer

    _init_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("")

    # Redirect _HALYARD_ACTIVE to a temp path so we don't touch the real one.
    active_path = tmp_path / ".halyard" / "active"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active_path)

    successes: list[int] = []
    failures: list[int] = []

    def _try_start(i: int) -> None:
        try:
            start_timer(tmp_path, "acme:auth")
            successes.append(i)
        except TimerAlreadyRunning:
            failures.append(i)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(_try_start, range(50)))

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    assert len(failures) == 49, f"Expected 49 failures, got {len(failures)}"

    # Exactly one clock-in entry in the timeclock
    i_lines = [
        line
        for line in (tmp_path / "time.timeclock").read_text().splitlines()
        if line.startswith("i ")
    ]
    assert len(i_lines) == 1, f"Expected 1 clock-in line, got {len(i_lines)}"


# ---------------------------------------------------------------------------
# Task 7.3: CLI stop + dashboard stop simultaneously → exactly one ``o`` line
# ---------------------------------------------------------------------------


def test_concurrent_stop_timer_produces_exactly_one_o_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two concurrent stop_timer calls must produce exactly one clock-out line."""
    from halyard.orchestration import start_timer, stop_timer

    _init_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("")

    active_path = tmp_path / ".halyard" / "active"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active_path)

    # Start the timer so there is something to stop.
    start_timer(tmp_path, "acme:auth")

    results: list[object] = []

    def _try_stop() -> None:
        results.append(stop_timer(tmp_path))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: _try_stop(), range(2)))

    o_lines = [
        line
        for line in (tmp_path / "time.timeclock").read_text().splitlines()
        if line.startswith("o ")
    ]
    assert len(o_lines) == 1, f"Expected exactly 1 clock-out line, got {len(o_lines)}"


# ---------------------------------------------------------------------------
# Task 7.4: Concurrent invoice allocation → unique numbers (no duplicates)
# ---------------------------------------------------------------------------


def test_concurrent_invoice_allocation_unique_numbers(tmp_path: Path) -> None:
    """Concurrent _allocate_invoice_number calls must each receive a unique counter."""
    import tomllib

    import tomli_w

    from halyard.invoicing import _allocate_invoice_number

    # Minimal halyard.toml with an invoicing section.
    toml_path = tmp_path / "halyard.toml"
    toml_path.write_text(tomli_w.dumps({"invoicing": {"counter": 0}}))

    allocated: list[int] = []

    def _alloc(_: int) -> None:
        allocated.append(_allocate_invoice_number(toml_path))

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(_alloc, range(20)))

    # Every allocated number must be unique.
    assert len(allocated) == 20
    assert len(set(allocated)) == 20, f"Duplicate invoice numbers: {sorted(allocated)}"

    # The on-disk counter must equal 20 after 20 allocations.
    final = tomllib.loads(toml_path.read_text())
    assert final["invoicing"]["counter"] == 20  # type: ignore[index]


# ---------------------------------------------------------------------------
# Task 7.5: Concurrent backfill_window + append_session → append survives
# ---------------------------------------------------------------------------


def test_concurrent_backfill_and_append_no_lost_sessions(tmp_path: Path) -> None:
    """append_session calls interleaved with backfill_window must not lose sessions."""
    from halyard.ai_log import backfill_window

    _init_project(tmp_path)

    # Seed with 10 unattributed sessions in the backfill window.
    start_dt = datetime(2026, 1, 1, 9, 0, 0)
    end_dt = datetime(2026, 1, 1, 10, 0, 0)
    for _ in range(10):
        append_session(
            tmp_path,
            _session(project=None, start=start_dt, end=datetime(2026, 1, 1, 9, 30, 0)),
        )

    def _backfill(_: int) -> None:
        backfill_window(tmp_path, start_dt, end_dt, "acme:auth")

    def _append(i: int) -> None:
        # Append sessions with timestamps outside the backfill window so they
        # are not candidates for attribution — they should survive regardless.
        append_session(
            tmp_path,
            _session(
                project="acme:dash",
                start=datetime(2026, 1, 2, 9, 0, 0),
                end=datetime(2026, 1, 2, 9, 30, 0),
            ),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        backfill_futures = [pool.submit(_backfill, i) for i in range(5)]
        append_futures = [pool.submit(_append, i) for i in range(20)]
        for f in backfill_futures + append_futures:
            f.result()

    log_path = tmp_path / AI_LOG_FILENAME
    s_lines = [line for line in log_path.read_text().splitlines() if line.startswith("s ")]
    # 10 seeded sessions + 20 concurrent appends = 30 total
    assert len(s_lines) == 30, f"Expected 30 session lines, got {len(s_lines)}"


# ---------------------------------------------------------------------------
# Task 6.4: Malformed log line in backfill → warning on stderr + log entry
# ---------------------------------------------------------------------------


def test_backfill_error_logs_to_halyard_log_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """When backfill_window raises, stop_timer must emit a warning and write to halyard.log."""
    from halyard.orchestration import start_timer, stop_timer

    _init_project(tmp_path)
    (tmp_path / "time.timeclock").write_text("")

    active_path = tmp_path / ".halyard" / "active"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("halyard.reports._HALYARD_ACTIVE", active_path)

    # Redirect halyard.log to a temp path to avoid polluting ~/.halyard/halyard.log
    halyard_log = tmp_path / "halyard.log"
    monkeypatch.setattr("halyard.ai_log._HALYARD_LOG", halyard_log)

    # Start the timer.
    start_timer(tmp_path, "acme:auth")

    # Patch backfill_window to raise so we can test the error path.
    def _broken_backfill(*args: object, **kwargs: object) -> int:
        raise ValueError("injected backfill failure")

    monkeypatch.setattr("halyard.orchestration.backfill_window", _broken_backfill)

    result = stop_timer(tmp_path)

    # Timer was running; result marks was_running True even though backfill failed.
    assert result.was_running is True

    # A warning must have been printed (stop_timer uses Console; captured via capsys
    # or Rich console — check stderr or stdout for the warning text).
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Warning" in combined or "backfill" in combined.lower(), (
        f"Expected a warning about backfill, got: {combined!r}"
    )

    # The halyard.log must contain the error entry.
    assert halyard_log.exists(), "halyard.log was not created"
    log_content = halyard_log.read_text()
    assert "backfill_window failed" in log_content
    assert "injected backfill failure" in log_content
