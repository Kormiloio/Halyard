# Proposal: v3.1 — Review-friction signals

## Why

v3.0 answers "did this AI session ship?" (branch → PR → merged). It does
not answer "how *hard* was it to ship?" Two sessions that both end in a
merged PR are not equal: one merged in 40 minutes with zero review
comments; the other took four days, three rounds of requested changes,
and 27 review comments. The second is the one a CTO cares about — it is
where AI-assisted work is generating downstream human cost.

This is the highest-leverage of the three deferred v3.1 workstreams
because it serves the enterprise ROI through-line directly: *is AI spend
producing low-friction shipped work, or shipped-but-expensive work?*
Cycle time and review burden are the metrics engineering leaders already
track; tying them to AI sessions is the differentiated signal.

The investor pressure test names review friction explicitly as part of
the outcome graph; v3.0 deferred it because it needs richer GitHub data
than `gh pr list` provides. v3.1 closes that gap.

## What changes

Three review-friction signals attached to an already-resolved PR linkage
(this changeset depends on v3.0's `pr_ref` resolution; it never does its
own branch→PR matching):

1. **Review-comment count** — number of review comments + review-thread
   comments on the linked PR.
2. **Review round-trips** — count of reviews with state
   `CHANGES_REQUESTED` (how many times the PR bounced back).
3. **Time-to-merge** — seconds between PR `createdAt` and `mergedAt`
   (only when `pr_state = merged`).

Plus the final `reviewDecision` enum (`APPROVED` /
`CHANGES_REQUESTED` / `REVIEW_REQUIRED` / none) as a captured label.

Surfaces:

- `halyard outcome sync` enriches each resolved PR with the four fields
  in the same pass (≤2 `gh` calls per *unique PR* — `gh pr view` plus
  `gh api .../pulls/<n>/comments` for inline review comments; both
  cached, see Phase-0 findings in `design.md`).
- `halyard outcome report` gains a friction breakdown: median
  time-to-merge and median review comments per outcome bucket.
- The Leverage panel (web + TUI parity) gains a one-line friction
  summary under the merged-percentage rollup.
- Invoice evidence appendix PR rows gain "merged in Nh, R rounds" — no
  comment text, integers only.

Data shape:

- New `a` correction-record keys: `review_comments`, `review_rounds`,
  `time_to_merge_s`, `review_decision`.
- New `outcomes` table columns (additive SQLite migration on the v3.0
  schema): `review_comment_count`, `review_round_trips`,
  `time_to_merge_seconds`, `review_decision`.
- Reuses the existing `pr_cache` table and TTL — the enriched query
  payload supersedes the lighter v3.0 payload for the same cache key.
- Trust label: `captured` (all four are read directly from the GitHub
  API via `gh`, not inferred).

## What stays the same

- v3.0's privacy contract holds verbatim and is the binding constraint:
  **only integers, ISO timestamps, and a fixed enum are stored.** No
  review comment body, no PR title, no diff, no source, no prompt text
  is ever read, stored, or transmitted.
- Local-first: data comes from `gh` on the user's machine with their
  existing credentials. No new token, no phone-home.
- `outcomes.enabled = false` disables this exactly as it disables v3.0.
- Plain-text log stays the source of truth; all four fields flow through
  v2.17 `a` correction records.
- If `gh` is absent or the API call fails, the four fields are simply
  absent — never an error, never a partial write.

## Out of scope

- Tool errors / approval rejections — separate v3.1-sibling workstream,
  needs collector enhancement, not GitHub data. Not this changeset.
- MCP-server inventory — separate v3.1-sibling workstream. Not this
  changeset.
- Per-reviewer identity, comment sentiment, or any LLM judgment of
  review quality. Halyard surfaces counts; humans interpret.
- GitLab / Bitbucket review data (gh-only for now; the field shape is
  forward-compatible if a second provider lands later).
- Re-resolving branch→PR linkage. v3.1 strictly enriches PRs that v3.0
  already resolved.

## Prerequisites

- v3.0 outcome graph code-complete (it is — roadmap entry 54).
- **Phase-0 spike (gating, see `design.md`):** confirm a single
  `gh pr view <ref> --json reviews,comments,reviewDecision,createdAt,mergedAt`
  call returns all four signals without N+1 pagination, that it stays
  inside the authenticated rate budget for a realistic sync, and that
  the degraded paths (no gh, private-repo 403, rate-limit 403) fail
  closed to "field absent." No production code merges before the spike
  resolves the open questions in `design.md`.

## Success criteria

1. On a project where v3.0 already resolves PRs, `halyard outcome sync`
   populates all four review-friction fields for ≥90% of sessions whose
   `pr_state` is `merged` or `closed`.
2. The enriched sync adds at most two `gh` calls per *unique PR ref*
   (not per session): `gh pr view` + the inline-comments API. Merged
   PRs are cached permanently (friction is immutable); only open /
   closed-unmerged PRs honour the `pr_cache` TTL.
3. Privacy fuzz test extended: sensitive markers seeded into PR review
   comment bodies, titles, and branch names never appear in the log,
   the cache payload, the report, or the invoice appendix.
4. Degraded-path tests: no `gh`, 403 (private/forbidden), 403
   (rate-limited), and `closed-unmerged` (no `time_to_merge_s`) each
   produce a clean partial result, not an exception.
5. Test suite gains ≥25 new tests across enrichment parsing, the report
   friction breakdown, cache reuse, and the privacy/degraded paths.

## Strategic implication

v3.0 made "did it ship?" present tense. v3.1 makes "what did shipping
cost?" present tense — the metric that turns Halyard from "AI activity
record" into "AI ROI record," which is the enterprise wedge.

## Detailed design

See `design.md`.
