# v5.23 — Tasks

## Code

- [x] `_ledger_duplicate_checks(project_dir, hub_dir)` in `doctor.py`:
      one raw-line pass per ledger, byte-identical `s`-line counter +
      per-`job_id` stalled-row counter, resolved-path dedup of
      (project, hub).
- [x] Wire into `build_doctor_report`.
- [x] `warning` only; detail carries counts + worst offender; fix carries
      the investigate-then-compact remediation.

## Tests (`tests/test_v523_ledger_duplicate_doctor.py`)

- [x] Byte-identical duplicate `s` rows → warning with surplus count,
      distinct-line count, and worst repeat count (the 143× scenario).
- [x] Clean ledger (unique rows, small job_id groups) → no ledger checks,
      report not degraded.
- [x] ≥ 5 *stalled* rows sharing one `job_id` with distinct line content →
      `ledger.job_rows` warning naming the job_id (byte-identity alone
      would miss it).
- [x] Long-lived growth re-import (50 advancing rows, one job_id) → no
      warning (pins the live false positive that forced the stalled-row
      design).
- [x] Below-threshold stalled rows (e.g. re-append after a state reset) →
      no warning.
- [x] Project and hub pointing at the same dir → scanned once (one check,
      not two).
- [x] Both checks are `warning`, never `error` (exit-code contract).
- [x] Comment / blank / `a` amendment lines never counted.

## Gates

- [x] `ruff check` + `ruff format --check` clean.
- [x] `mypy src/` clean.
- [x] Full pytest suite green.

## Spec sync

- [x] Roadmap entry in `openspec/project.md`; test count updated.

## Pulled into scope during verification

- [x] Raw same-job_id row-count threshold (20) replaced with a stalled-row
      count (≥ 5): the first live `halyard doctor` run flagged a legitimate
      3-day codex session (48 advancing growth re-import rows) — no fixed
      raw count separates a long-lived live session from a loop. Growth
      always advances end time/tokens; loops never do. See design.md.

## Follow-up (first live catch, 2026-06-11)

- [x] The canary's first real finding was the test suite itself: two v5.21
      test rows (`session_id=11111111-…`) had been direct-written into the
      developer's real hub ledger. `_no_real_hub` blocks the Hub daemon
      HTTP path, but `find_hub()` still read the real `~/.halyard/hub`
      pointer and `append_session` fell back to a direct file write.
      New autouse `_no_real_hub_pointer` conftest fixture redirects the
      pointer to a temp path (tests provision their own via `set_hub`).
      Leaked rows removed from the hub ledger (backup taken).
