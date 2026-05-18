# Spec: Review-friction signals

Requirements in WHEN/THEN form. All requirements are subordinate to the
v3.0 privacy contract (`../../v3.0-outcome-graph/specs/privacy-contract.md`):
nothing here may read, store, or transmit free text.

## R1 — Enrichment is layered on resolved PRs

- WHEN `halyard outcome sync` runs AND a session already has a resolved
  `pr_ref` (from v3.0), THEN the friction pass attempts to enrich that
  PR with `review_comments`, `review_rounds`, `time_to_merge_s`, and
  `review_decision`.
- WHEN a session has no resolved `pr_ref`, THEN no friction fields are
  written for it and no `gh` call is made on its behalf.
- WHEN multiple sessions resolve to the same `pr_ref`, THEN at most two
  `gh` invocations are made for that PR per cache window (`gh pr view`
  plus the inline-comments API) and every such session receives the
  same friction values.
- WHEN a PR's `pr_state = merged`, THEN its friction cache entry is
  valid permanently (friction is immutable post-merge) and the
  `pr_cache` TTL is ignored for that key; open / closed-unmerged PRs
  honour the existing TTL.

## R2 — Field semantics

- WHEN a PR has N reviews with state `CHANGES_REQUESTED`, THEN
  `review_rounds = N` (N may be 0).
- WHEN both calls succeed, THEN `review_comment_count =
  len(pr_view.comments) + len(pulls/<n>/comments)` (issue/timeline
  comments plus inline review-thread comments).
- WHEN `gh pr view` succeeds but the inline-comments API fails, THEN
  `review_comment_count` is absent (NOT the partial issue-comment
  count, NOT 0) while the other three fields are still written.
- WHEN a PR has `pr_state = merged`, THEN
  `time_to_merge_s = round((mergedAt - createdAt).total_seconds())`,
  a non-negative integer.
- WHEN a PR is `closed-unmerged` or `open`, THEN `time_to_merge_s` is
  absent (not 0).
- WHEN the GitHub API reports a review decision, THEN `review_decision`
  is one of `APPROVED`, `CHANGES_REQUESTED`, `REVIEW_REQUIRED`;
  otherwise the field is absent.
- WHEN any friction field is written, THEN its trust label is
  `captured`.

## R3 — Degraded paths fail closed

- WHEN `gh` is not installed or not authenticated, THEN the friction
  pass is skipped entirely, v3.0 resolution results are still written,
  and no error is raised.
- WHEN `gh pr view` for a specific PR returns 403/404 or times out,
  THEN that PR's four friction fields are left absent, other PRs in the
  same sync are still enriched, and no exception propagates.
- WHEN the `pulls/<n>/comments` endpoint returns 404/403 (e.g. the ref
  is not a PR), THEN only `review_comment_count` is left absent; the
  round-trips, time-to-merge, and decision fields from the successful
  `gh pr view` call are still written; no exception propagates.
- WHEN the `gh` JSON is missing an expected key, THEN only the fields
  derivable from present keys are written and the rest are absent
  (never defaulted to 0).
- WHEN a partial parse occurs, THEN no `outcomes` row is written with a
  mix of real and placeholder values — only genuinely parsed fields are
  upserted.

## R4 — Privacy

- WHEN the friction pass calls `gh pr view`, THEN the `--json` field
  list is exactly `number,state,createdAt,mergedAt,reviewDecision,
  reviews,comments` — never `body`, `bodyText`, `title`, or author
  identity fields; only `reviews[].state` and the comment-array
  *lengths* are read.
- WHEN the friction pass calls `gh api .../pulls/<n>/comments`, THEN
  the response is reduced to its `length` only; no comment body,
  author, or path is read or stored.
- WHEN friction data is persisted (log `a` record, `outcomes` table) or
  rendered (report, Leverage panel, invoice appendix), THEN only the
  four integer/enum values appear; no review text, PR title, branch
  name, or author appears.
- WHEN the privacy fuzz test seeds sensitive markers into PR comment
  bodies, PR title, and branch name, THEN none of those markers appears
  in the log, the `pr_cache` payload that is eligible for egress, the
  report output, or the invoice appendix.

## R5 — Config gating

- WHEN `[outcomes].enabled = false` in `halyard.toml`, THEN the friction
  pass does no work and makes no `gh` calls, identical to v3.0 behavior.
- WHEN `outcomes` is enabled but `gh` is unavailable, THEN sync still
  completes with v3.0 fields and no friction fields (R3).

## R6 — Surfaces

- WHEN `halyard outcome report` runs AND friction data exists, THEN each
  outcome bucket additionally shows median `time_to_merge_s` (humanized,
  e.g. "3h 12m") and median `review_comments`.
- WHEN no friction data exists for a bucket, THEN the report shows the
  bucket exactly as in v3.0 (no empty friction columns, no crash).
- WHEN the Leverage panel renders (web and TUI) AND friction data
  exists, THEN it shows a one-line summary (median time-to-merge,
  median review comments over the rollup window) under the existing
  merged-percentage line, within the existing 10-second / 100k-line
  refresh budget.
- WHEN the invoice evidence appendix lists a PR ref AND friction data
  exists, THEN the row appends "merged in <duration>, <N> review
  rounds" using integers only.

## R7 — Schema migration is additive

- WHEN a cache built on the v3.0 schema is opened by v3.1, THEN the
  additive migration adds the four `outcomes` columns, existing rows
  read back with `NULL` friction, and no `db reset` is required.
- WHEN a v3.0-era session is re-synced under v3.1, THEN its friction
  fields are backfilled in place via a v2.17 `a` correction record (the
  original record is never mutated).
