# Tasks — v5.9 Review remediation

- [x] #1 `ai_log`: `_release_read_lock` (win32 no-op / posix LOCK_UN / no-fcntl
      no-op); `read_locked_file` uses it.
- [x] #8 `ai_log.parse_sessions`: read lines under the lock, parse after release.
- [x] #6 `attribution.load_project_aliases`: mtime cache.
- [x] #4 `attribution.canonical_project`: transitive resolution + cycle guard.
- [x] #5 `budget`/`invoicing`: canonicalize config slug before matching.
- [x] #9 `hub_server`: canonicalize the live collision project slug.
- [x] #3 `hub_server._process_write_queue`: per-item try/except + diagnostic.
- [x] #2 `dashboard` reset handler: also clear `halyard-removed-v1`.
- [x] #7 `dashboard._overview_panels`: outcomes dedupe by `pr_ref`.
- [x] Tests (`test_v59_review_remediation.py`, +6); ruff + mypy clean; full
      suite green (1516).
- [x] Browser-verified reset restores hidden panels; roadmap entry 83.
