"""Regression tests for B06 — OTel receiver robustness (v5.18).

Four sub-defects of the audit blocker, each with a malicious/buggy case
and a benign case to guard against over-restriction:

1. (:187 slowloris)  request handler must set ``timeout`` so a slow /
   half-open client cannot pin a ThreadingHTTPServer worker thread.
2. (:100 thread death)  ``_flush_loop`` must survive a raise in
   ``_finalize_one`` so the only flush thread never dies permanently.
3. (:116 data loss)  ``flush_stale`` must finalize-then-pop (re-queue on
   failure) so a mid-loop raise does not silently drop later sessions.
4. (:56 unbounded cardinality)  ``_acc`` must be bounded; eviction must
   FINALIZE the evicted session, never silently drop it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from halyard.collectors import otel_receiver
from halyard.collectors.otel_receiver import _MAX_SESSIONS, OTelReceiver
from halyard.collectors.vscode_otel import _SessionAcc


def _acc(sid: str, *, last_update: datetime | None = None) -> _SessionAcc:
    a = _SessionAcc(session_id=sid)
    if last_update is not None:
        a.last_update = last_update
    return a


# ── B06.1 slowloris — handler sets a read timeout ───────────────────────


def test_handler_sets_read_timeout_against_slowloris() -> None:
    """Malicious/half-open client: the handler class must bound socket reads."""
    receiver = OTelReceiver(None, port=0)
    handler_cls = receiver._handler()
    assert handler_cls.timeout == 10


def test_handler_timeout_matches_sibling_hub_server() -> None:
    """Benign invariant: the bound mirrors hub_server's handler (10s)."""
    receiver = OTelReceiver(None, port=0)
    # A positive, finite timeout — not None (which would mean "block forever").
    assert isinstance(receiver._handler().timeout, int | float)
    assert receiver._handler().timeout > 0


# ── B06.2 thread death — _flush_loop survives a raise ───────────────────


class _BoomOnce:
    """flush_stale stub: raise the first call, succeed thereafter."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *, force: bool = False) -> int:
        self.calls += 1
        if self.calls == 1:
            raise FileNotFoundError("deleted cwd during finalize")
        return 0


def test_flush_loop_survives_exception_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Buggy case: a raise in flush_stale must not kill the daemon thread."""
    receiver = OTelReceiver(None, port=0)

    boom = _BoomOnce()
    monkeypatch.setattr(receiver, "flush_stale", boom)
    # log_diagnostic must be reachable and not itself raise.
    logged: list[str] = []
    monkeypatch.setattr(
        "halyard.ai_log.log_diagnostic",
        lambda msg, **kw: logged.append(msg),
    )

    # Drive _flush_loop deterministically: wake twice, then stop. The first
    # wake raises (and must be swallowed), the second wake runs cleanly.
    waits = iter([False, False, True])
    monkeypatch.setattr(receiver._stop, "wait", lambda _t: next(waits))

    # If _flush_loop did not guard the body, the first raise would propagate
    # out of this call and the second flush would never run.
    receiver._flush_loop()

    assert boom.calls == 2  # survived the raise and looped again
    assert logged and "flush_loop error" in logged[0]


def test_flush_loop_benign_runs_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Benign case: with no error, the loop flushes every wake without noise."""
    receiver = OTelReceiver(None, port=0)
    calls = {"n": 0}

    def _ok(*, force: bool = False) -> int:
        calls["n"] += 1
        return 0

    monkeypatch.setattr(receiver, "flush_stale", _ok)
    logged: list[str] = []
    monkeypatch.setattr(
        "halyard.ai_log.log_diagnostic",
        lambda msg, **kw: logged.append(msg),
    )
    waits = iter([False, False, True])
    monkeypatch.setattr(receiver._stop, "wait", lambda _t: next(waits))

    receiver._flush_loop()

    assert calls["n"] == 2
    assert logged == []  # no diagnostic noise on the happy path


# ── B06.3 data loss — flush_stale re-queues on a mid-loop raise ─────────


def test_flush_stale_requeues_unfinalized_sessions_on_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Buggy case: a raise mid-flush must not drop the not-yet-finalized sessions.

    The old code popped every ready session up front, so any raise lost
    sessions N..end. Now sessions remain in _acc to retry next tick.
    """
    receiver = OTelReceiver(None, port=0)
    stale = datetime.now() - timedelta(hours=1)
    for sid in ("A", "B", "C"):
        receiver._acc[sid] = _acc(sid, last_update=stale)

    finalized: list[str] = []

    def _finalize(acc: _SessionAcc) -> bool:
        if acc.session_id == "B":
            raise FileNotFoundError("git shellout failed on deleted cwd")
        finalized.append(acc.session_id)
        return True

    monkeypatch.setattr(receiver, "_finalize_one", _finalize)

    with pytest.raises(FileNotFoundError):
        receiver.flush_stale(force=True)

    # The failing session AND every session not yet reached must survive in
    # _acc so the next tick retries them — none are silently lost.
    remaining = set(receiver._acc)
    assert "B" in remaining  # re-inserted on failure
    # Sessions that already finalized successfully are gone.
    for done in finalized:
        assert done not in receiver._acc
    # Nothing was permanently dropped: finalized + remaining == original set.
    assert set(finalized) | remaining == {"A", "B", "C"}


def test_flush_stale_benign_finalizes_and_pops_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Benign case: with no error every stale session is finalized and removed."""
    receiver = OTelReceiver(None, port=0)
    stale = datetime.now() - timedelta(hours=1)
    for sid in ("X", "Y"):
        receiver._acc[sid] = _acc(sid, last_update=stale)
    # A fresh session must NOT be flushed without force (guard over-restriction).
    receiver._acc["FRESH"] = _acc("FRESH", last_update=datetime.now())

    finalized: list[str] = []
    monkeypatch.setattr(
        receiver,
        "_finalize_one",
        lambda acc: (finalized.append(acc.session_id), True)[1],
    )

    count = receiver.flush_stale()  # no force

    assert count == 2
    assert set(finalized) == {"X", "Y"}
    assert set(receiver._acc) == {"FRESH"}  # fresh session preserved


# ── B06.4 unbounded cardinality — eviction finalizes, never drops ───────


def test_ingest_finalizes_evicted_sessions_over_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malicious id-spray: over-cap sessions must be evicted by FINALIZING them.

    The eviction must not silently drop an in-flight session, and _acc must
    stay bounded at the cap.
    """
    receiver = OTelReceiver(None, port=0)

    finalized: list[str] = []
    monkeypatch.setattr(
        receiver,
        "_finalize_one",
        lambda acc: (finalized.append(acc.session_id), True)[1],
    )

    # Pre-fill to exactly the cap with strictly increasing last_update so the
    # eviction order (oldest first) is deterministic. "old-0" is stalest.
    base = datetime.now() - timedelta(hours=2)
    for i in range(_MAX_SESSIONS):
        sid = f"old-{i}"
        receiver._acc[sid] = _acc(sid, last_update=base + timedelta(seconds=i))

    # Now spray three brand-new session ids via the real ingest path. Each
    # new id pushes us one over the cap, evicting the stalest in-flight one.
    def _spray(sid: str) -> None:
        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [{"key": "session.id", "value": {"stringValue": sid}}]
                    },
                    "scopeSpans": [{"spans": [{"name": "chat"}]}],
                }
            ]
        }
        receiver.ingest_traces(payload)

    for sid in ("spray-A", "spray-B", "spray-C"):
        _spray(sid)

    # Cardinality stayed bounded — no OOM-by-id-spray.
    assert len(receiver._acc) == _MAX_SESSIONS
    # The three stalest in-flight sessions were FINALIZED on eviction, not
    # silently dropped.
    assert finalized == ["old-0", "old-1", "old-2"]
    # The fresh sprayed ids are retained in the accumulator.
    assert {"spray-A", "spray-B", "spray-C"} <= set(receiver._acc)


def test_ingest_under_cap_does_not_evict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Benign case: ordinary traffic under the cap is never finalized early."""
    receiver = OTelReceiver(None, port=0)
    finalized: list[str] = []
    monkeypatch.setattr(
        receiver,
        "_finalize_one",
        lambda acc: (finalized.append(acc.session_id), True)[1],
    )

    payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "session.id", "value": {"stringValue": "S1"}}]},
                "scopeSpans": [{"spans": [{"name": "chat"}]}],
            }
        ]
    }
    receiver.ingest_traces(payload)

    assert finalized == []  # nothing evicted/finalized under the cap
    assert "S1" in receiver._acc


def test_evict_helper_returns_oldest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit guard on the eviction helper: pops least-recently-updated first."""
    receiver = OTelReceiver(None, port=0)
    base = datetime.now() - timedelta(hours=1)
    # One over the cap; the single stalest must be the one evicted.
    for i in range(_MAX_SESSIONS + 1):
        sid = f"s-{i}"
        receiver._acc[sid] = _acc(sid, last_update=base + timedelta(seconds=i))

    evicted = receiver._evict_over_cap_locked()

    assert [a.session_id for a in evicted] == ["s-0"]
    assert "s-0" not in receiver._acc
    assert len(receiver._acc) == _MAX_SESSIONS


def test_module_exposes_session_cap() -> None:
    """The cardinality cap is a defined, positive bound."""
    assert isinstance(otel_receiver._MAX_SESSIONS, int)
    assert otel_receiver._MAX_SESSIONS > 0
