# Tasks

Implementation checklist for v3.1 — Review-friction signals.

## 0. Prerequisites

- [x] 0.1 v3.0 outcome graph code-complete (roadmap entry 54).
- [x] 0.2 **Phase-0 spike (gating)** — done 2026-05-17. S1: one-call
  assumption FALSE → ≤2 calls/PR (`gh pr view` + `gh api
  pulls/<n>/comments`). S2: rate budget ample. S3: degraded paths
  enumerated. OQ1/2/3 resolved. Findings appended to `design.md`;
  proposal + spec reconciled to the two-call shape.

## 1. Schema and amendment keys

- [x] 1.1 Added `_MIGRATIONS` tuple `(4, …)` in `db.py`: four additive
  `ALTER TABLE outcomes ADD COLUMN` statements; `_CURRENT_VERSION`
  4→5; `_CREATE_SCHEMA_V1` outcomes table updated for fresh DBs.
  Verified additive + idempotent self-heal on a simulated v4 cache.
- [x] 1.2 Added optional `AiSession` fields: `review_comments`,
  `review_rounds`, `time_to_merge_s` (`int|None`), `review_decision`
  (`str|None`).
- [x] 1.3 `apply_amendment` + `to_log_line` + `_parse_line_result`
  handle the four new `a` keys; round-trip + byte-stability verified,
  empty case still byte-identical (v2.75 path unaffected). ruff/mypy
  clean; 1286 tests green.

## 2. Enrichment collector

- [x] 2.1 `gh_pr_view` (privacy-restricted `--json
  number,state,createdAt,mergedAt,reviewDecision,reviews,comments`) +
  `gh_pr_inline_comment_count` (`gh api .../pulls/<n>/comments --jq
  length`) in `outcomes.py`; both fail closed to None.
- [x] 2.2 `parse_friction(pr_view, inline_comment_count)` — pure;
  `review_comments = len(comments)+inline` only when both present;
  `review_rounds` = CHANGES_REQUESTED count; `time_to_merge_s` merged
  only and ≥0; `review_decision` enum-validated; all fail-closed to
  None (no zero defaults). Edge cases hand-verified.
- [x] 2.3 `_resolve_friction` + per-sync `friction_memo` (≤2 gh calls
  per unique `pr_ref`); `:friction` cache namespace;
  `_friction_cache_get/_set` — merged PRs permanent, open/closed honour
  `_CACHE_TTL_HOURS`; total `gh pr view` failure not cached (retries).
- [x] 2.4 Wired into `resolve_sessions` (gated on `gh_available()`,
  skipped cleanly when absent); combined single `a` record per session
  + `_upsert_outcome` ON CONFLICT with COALESCE so friction-free writes
  never wipe prior enrichment. ruff/mypy clean; 1286 tests green
  (`_mem_db()` fixture now built from the real schema).

## 3. Surfaces

- [x] 3.1 `outcome report` — `OutcomeBucket` gains
  `median_time_to_merge_s`/`median_review_comments` (captured buckets
  only); `cli_outcome` prints a `└` friction sub-line only when the
  bucket has data; absent-data path renders v3.0-identical.
- [x] 3.2 Leverage panel (web) — `LeverageSummary` gains the two
  medians (shared `leverage.summarize`); `_leverage_panel` renders a
  `.leverage-friction` line under the caption only when data exists;
  pure read over existing fields, no extra refresh cost.
- [x] 3.3 Leverage panel (TUI) — `LeveragePane` renders the same
  medians via the shared `summarize` + `humanize_seconds`; parity with
  web (v2.70 lift); `last_rendered_text` unit-testable.
- [x] 3.4 Invoice evidence appendix — per-PR "merged in <dur>, <N>
  review rounds" cell; Friction column added only when ≥1 PR has data
  (else byte-identical to v3.0). Integers only, no text/title/branch.
  Shared `humanize_seconds`; ruff/mypy clean; 82 core + 222
  invoice/leverage/dashboard/outcome tests green.

## 4. Privacy contract

- [x] 4.1 `test_outcomes_privacy_fuzz.py`:
  `test_v31_friction_does_not_leak_gh_freetext` (5 trials) seeds a
  marker into PR title/body/bodyText, review bodies, comment bodies and
  asserts it never reaches the ReviewFriction values, the pr_cache
  payload, the log `a` record, the report, the Leverage panel, or the
  invoice appendix.
- [x] 4.2 `test_gh_pr_view_json_field_list_has_no_freetext_key` —
  captures the real `gh pr view` argv and asserts the `--json` set is
  exactly `{number,state,createdAt,mergedAt,reviewDecision,reviews,
  comments}` with no body/bodyText/title/author key.
- [x] 4.3 `test_outcomes_disabled_makes_no_gh_calls` — with
  `[outcomes] enabled = false`, `outcome sync` exits 0 and both
  `subprocess.run` and `resolve_sessions` are never called.

## 5. Tests (≥25 new) — 30+ added, suite 1286 → 1316

- [x] 5.1 8 `parse_friction` units: 0/1/N rounds, merged vs
  closed-unmerged vs open, missing keys, junk decision, negative
  duration, None payload.
- [x] 5.2 `test_resolve_friction_caches_and_dedups` (≤2 calls, 2nd
  served from cache), `test_friction_cache_merged_permanent_open_ttl`,
  `test_resolve_friction_total_failure_not_cached`.
- [x] 5.3 `gh pr view` nonzero/timeout/invalid-ref → None; inline
  404/non-numeric → None; `test_degraded_inline_only_keeps_other_three`
  (only `review_comments` absent, other three written) — no exception.
- [x] 5.4 `test_report_bucket_medians` +
  `test_report_absent_friction_is_v30_identical`.
- [x] 5.5 `test_migration_v4_to_v5_is_additive` (idempotent self-heal)
  + `test_friction_amendment_does_not_mutate_original_s_line`.
- [x] 5.6 `test_leverage_friction_web_tui_parity_and_perf` (same number
  in web + `LeveragePane.last_rendered_text`, `perf_ceiling(1.0)`, no
  bare wall-clock) + `test_leverage_no_friction_renders_v30_identical`.

## 6. Spec sync (close-out, same session as code)

- [x] 6.1 Ticked incrementally as items landed (§0–§5, not batched).
- [x] 6.2 `design.md`: Phase-0 findings recorded earlier; an
  "Implementation notes (close-out, 2026-05-17)" section records the
  refinements (combined `a` record, COALESCE upsert, no-cache on total
  failure, shared `leverage.summarize`, fixture drift fix). No spec/
  privacy deviation.
- [x] 6.3 Roadmap entry 55 added to `openspec/project.md` (1315 tests
  passing; +30 over v3.0). Entry 54's "next increment" wording
  retargeted to entry 55; no stale v3.1 bullet in Deferred-or-gated.
- [x] 6.4 `strategy/prd-outcome-graph.md` deferred list: review-friction
  struck through and marked SHIPPED in v3.1 (local edit only — never
  staged/committed per the hard rule).
- [x] 6.5 Archived to
  `openspec/changes/archive/2026-05-17-v3.1-review-friction/`.
