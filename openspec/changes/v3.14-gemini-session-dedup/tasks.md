# Tasks: v3.14 — Gemini session de-duplication

## Investigation (done)

- [x] Reproduced the over-count on the real `70615981` session (3 rows →
      147,186/2,990/365,090 vs `/quit` 59,970/1,451/170,196).
- [x] Root-caused Defect A (hook writes whole-session cumulative per turn),
      Defect B (importer duplicates the hook's final row; `_dedup_sessions`
      misses it), Defect C (utility model absent from the history source).

## Implementation

- [x] `ai_log._gemini_session_key` + `ai_log.collapse_gemini_sessions`
      (key from `session_id` or `gemini:` job_id; keep most-complete row).
- [x] Apply at the end of `parse_sessions` (after the synthetic/future filter).
- [x] Apply in `reports.build_aggregate_dashboard_state` after `_dedup_sessions`
      (cross-log case).

## Tests

- [x] Real-session regression: the three `70615981` rows collapse to one
      (59,970/1,451/170,196, project preserved).
- [x] Multi-turn hook-only cumulative snapshots → one canonical row.
- [x] Hook + importer duplicate → one row, attributed row preferred on tie.
- [x] Distinct gemini sessions not merged; non-gemini (claude per-turn) untouched.
- [x] Idempotency (collapse∘collapse == collapse) + order preserved + e2e parse.
- [x] No suite fallout; ruff / mypy / full suite green (1439 tests, +7).

## Docs

- [x] `docs/collector-coverage.md`: note the utility/router-model history-source
      limitation (Defect C).
- [x] `openspec/project.md` roadmap entry (v3.14).
- [x] CHANGELOG (Fixed).
