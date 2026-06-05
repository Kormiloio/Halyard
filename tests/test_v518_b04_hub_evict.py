"""v5.18 / B4-evict — OTel eviction must finalize, not silently drop.

When the in-flight OTel accumulator exceeds ``_MAX_OTEL_SESSIONS`` the
oldest sessions are evicted to bound memory. The pre-fix eviction did a
bare ``del self._otel_acc[sid]``, dropping genuine in-flight sessions
before they ever reached the ledger (HIGH data-loss). The eviction path
must instead finalize-and-write the evicted accumulator, the same way the
TTL flush path does.

Regression coverage:
(a) over-cap: an evicted accumulator with usable timing is written to the
    ledger rather than discarded;
(b) benign: under the cap, ingestion evicts/writes nothing (no
    over-restriction — normal in-flight sessions stay accumulating).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard import hub_server
from halyard.ai_log import AI_LOG_FILENAME
from halyard.collectors.vscode_otel import _SessionAcc
from halyard.hub_server import HubServer


def _ledger_lines(project_dir: Path) -> list[str]:
    """Raw ``s`` rows actually persisted to the ledger.

    Asserting on the raw file (not ``parse_sessions``) is deliberate: the
    read boundary filters synthetic-telemetry rows, but the data-loss
    surface this blocker is about is whether the bytes ever reach disk.
    """
    log = project_dir / AI_LOG_FILENAME
    if not log.exists():
        return []
    return [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.startswith("s ")]


def _usable_acc(sid: str, last_update: datetime) -> _SessionAcc:
    """An accumulator that ``finalize`` turns into a real AiSession."""
    acc = _SessionAcc(session_id=sid, last_update=last_update)
    acc.start = last_update
    acc.end = last_update + timedelta(seconds=30)
    acc.output_tokens = 7
    acc.chat_spans = 1
    return acc


def test_eviction_writes_evicted_session_to_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B4-evict: the oldest, over-cap session is finalized to the ledger,
    not silently dropped."""
    monkeypatch.setattr(hub_server, "_MAX_OTEL_SESSIONS", 2)
    server = HubServer(project_dir=tmp_path, port=0)

    base = datetime(2026, 6, 5, 9, 0, 0)
    # Three usable in-flight sessions, one over the cap of 2.
    for i in range(3):
        sid = f"sess-{i}"
        server._otel_acc[sid] = _usable_acc(sid, base + timedelta(minutes=i))

    # Any ingest re-checks the cap; an empty payload is tolerated and adds
    # nothing, so it isolates the eviction behavior.
    server.ingest_traces({})

    # The two most-recent survive in memory; the oldest is evicted.
    assert set(server._otel_acc) == {"sess-1", "sess-2"}

    # ...but the evicted oldest must have been finalized to the ledger.
    lines = _ledger_lines(tmp_path)
    assert len(lines) == 1
    assert "session_id=sess-0" in lines[0]
    # finalize carried the real accumulated usage through (output_tokens=7).
    assert " 0 7 " in lines[0]


def test_eviction_finalizes_via_write_to_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The eviction path routes through the same ``_write_to_log`` finalize
    sink the TTL flush uses (and only for the over-cap entries)."""
    monkeypatch.setattr(hub_server, "_MAX_OTEL_SESSIONS", 1)
    server = HubServer(project_dir=tmp_path, port=0)

    captured: list[str | None] = []
    monkeypatch.setattr(server, "_write_to_log", lambda s: captured.append(s.session_id))

    base = datetime(2026, 6, 5, 10, 0, 0)
    for i in range(3):
        sid = f"acc-{i}"
        server._otel_acc[sid] = _usable_acc(sid, base + timedelta(minutes=i))

    server.ingest_traces({})

    # Cap is 1: the two oldest are evicted and both finalized+written.
    assert captured == ["acc-0", "acc-1"]
    assert set(server._otel_acc) == {"acc-2"}


def test_under_cap_evicts_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Benign case: a normal, under-cap in-flight session is neither evicted
    nor prematurely written — guards against over-restriction."""
    monkeypatch.setattr(hub_server, "_MAX_OTEL_SESSIONS", 10)
    server = HubServer(project_dir=tmp_path, port=0)

    captured: list[str | None] = []
    monkeypatch.setattr(server, "_write_to_log", lambda s: captured.append(s.session_id))

    server._otel_acc["live"] = _usable_acc("live", datetime(2026, 6, 5, 11, 0, 0))

    server.ingest_traces({})

    # Still accumulating in memory, nothing flushed to the ledger early.
    assert set(server._otel_acc) == {"live"}
    assert captured == []
    assert _ledger_lines(tmp_path) == []


def test_eviction_skips_unfinalizable_accumulator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An evicted accumulator with no usable timing (finalize -> None) is
    dropped from memory without crashing the ingest path."""
    monkeypatch.setattr(hub_server, "_MAX_OTEL_SESSIONS", 1)
    server = HubServer(project_dir=tmp_path, port=0)

    base = datetime(2026, 6, 5, 12, 0, 0)
    # Oldest has no start -> finalize returns None (no real turn).
    server._otel_acc["empty"] = _SessionAcc(session_id="empty", last_update=base)
    server._otel_acc["real"] = _usable_acc("real", base + timedelta(minutes=1))

    server.ingest_traces({})

    assert set(server._otel_acc) == {"real"}
    # The unfinalizable one produced no ledger row, but did not raise.
    assert _ledger_lines(tmp_path) == []
