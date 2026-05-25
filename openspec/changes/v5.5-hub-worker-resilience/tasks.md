# Tasks — v5.5 Hub worker resilience + bounded OTel accumulator

- [x] `hub_server.py`: split `_worker_loop` into a scheduler + `_worker_tick`;
      wrap the tick in `try/except Exception` + `log_diagnostic` breadcrumb.
- [x] `hub_server.py`: add `_MAX_OTEL_SESSIONS` cap + `_evict_excess_otel()`;
      call it from `ingest_traces` under the existing lock.
- [x] Tests (`tests/test_v55_hub_resilience.py`): worker tick swallows + logs a
      raised error; accumulator capped oldest-first; no-op under the cap.
- [x] ruff + ruff format + mypy clean; full suite green.
- [x] Roadmap entry 79 in `openspec/project.md`.
