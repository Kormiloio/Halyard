# Design — v5.5 Hub worker resilience + bounded OTel accumulator

## #3a Worker-tick isolation

`_worker_loop` becomes a thin scheduler; the work moves to `_worker_tick`:

```python
def _worker_loop(self) -> None:
    while not self._stop.is_set():
        self._worker_tick()
        time.sleep(1)

def _worker_tick(self) -> None:
    try:
        self._process_write_queue()
        self.flush_stale()
        self._close_stale_presence()
    except Exception as exc:
        from halyard.ai_log import log_diagnostic
        log_diagnostic(f"hub_server: worker tick failed: {exc}")
```

Design points:
- **`except Exception`, not bare `except`** — `KeyboardInterrupt`/`SystemExit`
  still propagate; only operational errors are absorbed.
- **The breadcrumb is the point.** A swallowed error that leaves no trace is
  the very failure mode v5.3 added `diagnostic.log` for, so the handler records
  one line and the loop survives. Full tracebacks still go to the audit
  `halyard.log` from the deeper `_log_error` paths where present.
- **`time.sleep(1)` stays in the loop, outside the try** — so a tight error
  loop still paces at 1 Hz rather than spinning.
- **Testability** — extracting `_worker_tick` lets a test drive exactly one
  unit of work (monkeypatch `flush_stale` to raise, assert no propagation +
  a diagnostic line) without racing the daemon thread.

## #3b Bounded accumulator

`_MAX_OTEL_SESSIONS = 1000`. `ingest_traces` calls `_evict_excess_otel()` while
already holding `self._lock`:

```python
def _evict_excess_otel(self) -> None:
    excess = len(self._otel_acc) - _MAX_OTEL_SESSIONS
    if excess <= 0:
        return
    oldest = sorted(self._otel_acc.items(), key=lambda kv: kv[1].last_update)
    for sid, _acc in oldest[:excess]:
        del self._otel_acc[sid]
```

- **Oldest-by-`last_update` eviction** mirrors the existing TTL-flush ordering
  (idle sessions go first); an actively-updated session is never dropped while
  a stale one remains.
- **Lock discipline** — the method is documented as "call holding
  `self._lock`" and its only caller (`ingest_traces`) holds it. No separate
  lock acquisition, so no re-entrancy.
- **Cap rationale** — a real editor holds a handful of live `session.id`s; 1000
  is far above legitimate use and only trips under a local flood. Eviction is
  harmless: a dropped session simply isn't finalized (no partial/garbage row).

## Why not the full schema validator

`accumulate_traces` already type-guards every OTLP level and coerces numbers
via `_as_int` (returns `None` on garbage), and `to_log_line` sanitizes on
write. A per-field Pydantic model over the deeply-nested OTLP structure would
duplicate that defensive parsing for no additional guarantee, and would risk
rejecting valid-but-unexpected OTLP shapes (the format is extensible). The two
fixes here close the actual gaps (thread death, unbounded growth) that the
defensive parser did not.
