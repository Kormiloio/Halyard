# v5.5 — Hub worker resilience + bounded OTel accumulator

## Why

A security review recommended hardening the Hub's OTLP ingestion with a strict
per-field schema validator to prevent malformed attributes from causing DoS or
log-injection. Verifying the path showed most of that concern is already
covered:

- **Log-injection is structurally prevented** — OTLP data reaches
  `ai-sessions.log` only through `append_session` → `to_log_line`, which
  sanitizes every field (`_safe_field` / `_encode_free_text`). The write
  boundary, not the ingest boundary, is the injection guard (v2.38).
- **Body size is bounded** to 25 MB (`_read_body`) and the Hub binds loopback
  only.
- **`accumulate_traces` is already fully defensive** — it isinstance-guards
  every level and coerces ints via `_as_int`, skipping bad sub-trees rather
  than raising.

So a per-field OTLP Pydantic schema would be redundant. But verification
surfaced two real, narrow robustness gaps worth closing:

1. **The worker loop had no exception guard.** `_worker_loop` ran
   `_process_write_queue` / `flush_stale` / `_close_stale_presence` with no
   `try/except`. An unexpected error in any step would kill the daemon worker
   thread and silently halt *all* background writes — exactly the kind of
   invisible degradation v5.3's diagnostic log exists to surface.
2. **`_otel_acc` was unbounded by count.** Entries were only TTL-evicted
   (10 min). A local client emitting many distinct `session.id`s within the
   window could grow it without bound (local-only, but unbounded).

## What changes

1. **Worker-tick isolation.** Extract `_worker_tick()` (the three background
   steps) from `_worker_loop` and wrap it in `try/except Exception`; on error
   it records a one-line breadcrumb via `log_diagnostic` (the v5.3 seam) and
   the loop continues. One bad session can no longer stop the worker.
2. **Bounded accumulator.** New `_MAX_OTEL_SESSIONS` (1000) cap; after each
   `accumulate_traces`, `_evict_excess_otel()` drops the least-recently-updated
   sessions beyond the cap (holding `self._lock`). A real editor has very few
   live sessions, so legitimate use is unaffected.

## Impact

- Affected: `src/halyard/hub_server.py` (worker loop split + cap).
- New tests: `tests/test_v55_hub_resilience.py` — worker tick swallows + logs a
  raised error; accumulator capped oldest-first; no-op under the cap.
- No format/contract change; the OTLP and ingest endpoints are byte-compatible.
- **Out of scope (rejected from the review):** a per-field OTLP schema
  validator (redundant — see above); the pricing-signing recommendation (the
  existing HTTPS + origin-pin + SHA-256 TOFU already blocks silent changes);
  the token-access audit log (ineffective — the token is `0600` and a local
  attacker reads the file directly rather than calling the function).
