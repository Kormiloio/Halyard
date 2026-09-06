# v5.35 — Tasks

## Code

- [x] `_human_time_coverage_checks`: warn below 50% coverage, gated on ≥1 h
      of AI evidence.
- [x] Denominator excludes sessions past `_MAX_SESSION_SECONDS`, reusing
      v5.33's bound so the check and the reconciliation cannot disagree.
- [x] `_truncated_transcript_checks`: surface truncation events from the
      diagnostic log, naming files.
- [x] Both wired into `build_doctor_report`; both `warning`, never `error`.

## Tuning (a precondition from the v5.26 design)

- [x] Measured against real data: unbounded denominator gives 9.3% on a
      *healthy* machine; bounded gives 79.9%.
- [x] Validated in both directions on the maintainer's actual files —
      pre-recovery timeclock fires at 8%, post-recovery is silent.

## Tests (`tests/test_v535_doctor_coverage.py`)

- [x] Fires on an under-counted timeclock; silent when healthy.
- [x] Silent on a short day (below the evidence floor).
- [x] A 653 h session does not trip the check — the tuning finding, pinned.
- [x] Missing timeclock / no target dir are not findings.
- [x] Truncation in the log is surfaced and names the file.
- [x] An unrelated log line is not a finding; a missing log is not a finding.
- [x] Neither check can flip the exit code.

## Gates

- [x] `uv run pytest` — 1907 passing.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Out of scope (recorded)

- [ ] Predicting truncation by re-stat'ing transcripts on every doctor run.
- [ ] Per-day or per-project coverage breakdown.
