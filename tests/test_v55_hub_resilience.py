"""v5.5 — Hub worker resilience + bounded OTel accumulator.

#3a: a single bad session must not kill the daemon worker thread.
#3b: a local client spamming distinct session ids must not grow memory
     without bound — the OTel accumulator is capped, oldest-first.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from halyard import ai_log, hub_server
from halyard.collectors.vscode_otel import _SessionAcc
from halyard.hub_server import HubServer


def test_worker_tick_swallows_and_logs_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diag = tmp_path / "diagnostic.log"
    monkeypatch.setattr(ai_log, "_HALYARD_DIAG_LOG", diag)

    server = HubServer(project_dir=tmp_path, port=54321)

    def boom() -> int:
        raise RuntimeError("malformed session blew up flush")

    monkeypatch.setattr(server, "flush_stale", boom)

    # Must not raise — the daemon thread has to survive a bad tick.
    server._worker_tick()

    logged = diag.read_text()
    assert "hub_server: worker tick failed" in logged
    assert "malformed session blew up flush" in logged


def test_otel_accumulator_is_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hub_server, "_MAX_OTEL_SESSIONS", 3)
    server = HubServer(project_dir=tmp_path, port=54322)

    base = datetime(2026, 5, 24, 12, 0, 0)
    for i in range(6):
        sid = f"sess-{i}"
        server._otel_acc[sid] = _SessionAcc(session_id=sid, last_update=base + timedelta(seconds=i))

    server._evict_excess_otel()

    assert len(server._otel_acc) == 3
    # The three most-recently-updated survive; the oldest are evicted.
    assert set(server._otel_acc) == {"sess-3", "sess-4", "sess-5"}


def test_evict_is_noop_under_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hub_server, "_MAX_OTEL_SESSIONS", 10)
    server = HubServer(project_dir=tmp_path, port=54323)
    server._otel_acc["only"] = _SessionAcc(session_id="only")

    server._evict_excess_otel()

    assert set(server._otel_acc) == {"only"}
