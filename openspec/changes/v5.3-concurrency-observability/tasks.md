# Tasks — v5.3 Concurrency + observability hardening

- [x] `ai_log.py`: add `_acquire_read_lock` (LOCK_SH / Windows + no-fcntl
      no-ops) and `read_locked_file()` shared-lock context manager.
- [x] `ai_log.py`: `_iter_log_lines` takes a file handle; `parse_sessions` and
      `unattributed_log_count` read through `read_locked_file`; drop the stale
      "Read paths do not lock" docstring.
- [x] `ai_log.py`: add `log_diagnostic()` → `~/.halyard/diagnostic.log`
      (one-line, never raises); rename `_HALYARD_LOG` → `_HALYARD_AUDIT_LOG`.
- [x] `hub_client.py`: `log_diagnostic` on the `_request` degrade-to-None path.
- [x] `git_context.py`: `log_diagnostic` on every subprocess error/timeout path.
- [x] Tests (`tests/test_v53_concurrency_observability.py`): cross-process
      shared-lock wait; `log_diagnostic` writes one line; `log_diagnostic`
      never raises; Hub-timeout falls back to local write + diagnostic.
- [x] All diagnostic-touching tests isolate `_HALYARD_DIAG_LOG` to tmp_path.
- [x] Fix fallout from the `_HALYARD_LOG`→`_HALYARD_AUDIT_LOG` rename:
      `test_log_integrity.py` monkeypatched the old constant name.
- [x] ruff + ruff format + mypy clean on changed src + tests; full suite green
      (1495 passed).
- [x] Update `openspec/project.md` roadmap (entry 77; v5.4 → 78).
