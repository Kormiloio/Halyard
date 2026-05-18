# Design: v3.1 — Review-friction signals

## Phase-0 spike (gating — resolve before any production code)

v3.0 deliberately avoided the GitHub API beyond `gh pr list`. v3.1
crosses that line, so the spike de-risks the dependency before code:

**S1 — One-call sufficiency.** Confirm
`gh pr view <ref> --json number,state,createdAt,mergedAt,reviewDecision,reviews,comments`
returns review state, the changes-requested reviews, and comment counts
in a *single* call with no follow-up pagination for typical PRs
(< ~100 comments). Record the JSON shape actually returned (the
`reviews` array element schema and whether `comments` is the issue-
comment count or includes review-thread comments — these differ across
`gh` versions). The parser keys off the observed shape, not assumed.

**S2 — Rate budget.** `gh` uses the user's authenticated token
(5000 req/hr). One call per *unique PR ref* per TTL window. Confirm a
realistic `outcome sync` over a 90-day window stays well under budget,
and that the existing `pr_cache` TTL (currently 1h, `_CACHE_TTL_HOURS`
in `outcomes.py`) is the right reuse boundary. If a sync can plausibly
exceed budget, the spike must produce a backoff/parameter answer
(longer TTL for the enriched payload, or `--limit`-style capping)
*before* code.

**S3 — Degraded paths.** Enumerate and hand-verify the failure modes:
no `gh` binary, unauthenticated `gh`, repo not accessible (403/404),
secondary rate limit (403 with `Retry-After`), and `closed-unmerged`
(no `mergedAt`). Each must map to "field absent, no exception, no
partial DB write." The spike writes these down as the exact branches
the parser implements.

**Exit criterion:** S1–S3 answered in writing (appended to this file as
a "Phase-0 findings" section). Until then `tasks.md` §2+ stays blocked.

## Approach

v3.1 is an *enrichment pass layered on v3.0's resolution*, not a new
resolver. The data flow:

```
halyard outcome sync
  └─ v3.0: resolve_sessions()  → session → pr_ref, pr_state   (unchanged)
  └─ v3.1: for each UNIQUE resolved pr_ref:
             cache_key = f"{remote}:{pr_ref}:friction"
             payload  = pr_cache.get(cache_key) or gh_pr_view(pr_ref)
             friction = parse_friction(payload)
           write a-record:  review_comments, review_rounds,
                             time_to_merge_s, review_decision
           upsert outcomes columns
```

Key design decisions:

- **Enrich by unique PR, not by session.** Many sessions map to one PR;
  the friction of that PR is identical for all of them. Group by
  `pr_ref` before the `gh` call (mirrors how v3.0 already groups by
  branch in `resolve_sessions`). This is what makes success criterion 2
  achievable.
- **Separate cache key namespace.** The enriched payload is a superset
  of v3.0's `gh pr list` payload, so it gets its own
  `:friction`-suffixed `cache_key` rather than overloading the existing
  branch key. Same `pr_cache` table, same TTL helpers (`_cache_get` /
  `_cache_set` in `outcomes.py`) — no schema change to `pr_cache`.
- **Counts only, computed in Halyard.** `gh` returns arrays; Halyard
  reduces them to integers *in the parser* and the arrays are never
  persisted. `review_round_trips = len([r for r in reviews if
  r.state == "CHANGES_REQUESTED"])`. `review_comment_count` = issue
  comments + review-thread comments (final formula pinned by S1).
  `time_to_merge_seconds = (mergedAt - createdAt).total_seconds()` and
  is `NULL` unless `pr_state == merged`.
- **Fail closed.** Any parse/availability failure leaves all four
  fields unset; a partially parsed PR writes nothing for the missing
  fields rather than zeros (zero round-trips is a real, different value
  from "unknown").

## Schema

Additive migration appended to `_MIGRATIONS` in `db.py`. v3.0's last
migration is `(3, "ALTER TABLE sessions ADD COLUMN code_added INTEGER;")`,
so this is the `(4, …)` tuple:

```sql
ALTER TABLE outcomes ADD COLUMN review_comment_count INTEGER;
ALTER TABLE outcomes ADD COLUMN review_round_trips   INTEGER;
ALTER TABLE outcomes ADD COLUMN time_to_merge_seconds INTEGER;
ALTER TABLE outcomes ADD COLUMN review_decision      TEXT;
```

`SCHEMA_VERSION` bumps accordingly. No `REQUIRES_RESET` — purely
additive, existing rows get `NULL` and are backfilled on next sync.

Log amendment keys (v2.17 `a` records, v2.75 extensible-token safe):
`review_comments`, `review_rounds`, `time_to_merge_s`,
`review_decision`. These are additive optional `AiSession` fields with
`int | None` / `str | None` types and an enum-validated
`review_decision`.

## Privacy

The binding constraint. The only egress-eligible values are:

| Field                | Type    | Domain                                            |
|----------------------|---------|---------------------------------------------------|
| review_comment_count | int ≥0  | a count                                           |
| review_round_trips   | int ≥0  | a count                                           |
| time_to_merge_s      | int ≥0  | a duration                                        |
| review_decision      | enum    | APPROVED \| CHANGES_REQUESTED \| REVIEW_REQUIRED  |

The parser must read only `reviews[].state`, the comment *count*, and
the two timestamps from the `gh` JSON. It must never read `body`,
`title`, `bodyText`, author logins, or any free-text field, and those
keys are explicitly excluded from the `--json` field list so they are
never even fetched. The privacy fuzz test (extending v3.0's
`test_outcomes_privacy_fuzz.py`) seeds markers into comment bodies / PR
title / branch and asserts none reach any surface.

## Trust labels

All four are `captured` — read directly from the GitHub API, not
inferred or calculated. This is stronger than v3.0's `inferred`
shell-history signals and should be presented as such (the friction
numbers are authoritative, unlike attempt-tracking heuristics).

## Alternatives considered

- **GraphQL via `gh api graphql`** — one query could fetch everything
  including pagination cursors. Rejected for v3.1: `gh pr view --json`
  is simpler, already the idiom in `outcomes.py`, and S1 will confirm
  it is sufficient for typical PRs. Revisit only if S1 shows N+1.
- **Per-session enrichment** — simpler code, but violates success
  criterion 2 (one call per session, not per PR). Rejected.
- **Storing the raw `gh` JSON in `pr_cache`** — already what v3.0 does
  for the list payload; we keep that (it is a local cache the user
  owns, never egressed) but the *outcomes* table and the *log* get only
  the four reduced integers/enum. The redacted enterprise egress
  schema (v3.3) reads from `outcomes`, never from `pr_cache`.

## Open questions (answer in Phase-0)

1. Does `gh pr view --json comments` count review-thread comments or
   only top-level issue comments? Determines whether
   `review_comment_count` needs `reviews[].comments` summed too.
2. Is `reviewDecision` populated for already-merged PRs, or only open
   ones? If null-on-merged, derive the decision from the last
   non-dismissed review instead.
3. TTL: is 1h (v3.0 default) appropriate for friction data, which is
   stable once a PR is merged? Likely a longer TTL (or "infinite once
   `pr_state == merged`") — confirm and, if so, special-case merged
   PRs as permanently cacheable.

## Phase-0 findings (resolved 2026-05-17, gh 2.90.0)

Spike run against public PRs (rate cost ~28 calls of 5000/hr budget).

**S1 — one-call sufficiency: FALSE. Revised to two calls per PR.**
`gh pr view <ref> --json reviews,comments,reviewDecision,state,createdAt,mergedAt`
returns:
- `reviewDecision` — populated even on MERGED PRs (observed
  `APPROVED`). **OQ2 resolved:** no need to derive from last review.
- `reviews[]` element keys: `author, authorAssociation, body, commit,
  id, includesCreatedEdit, reactionGroups, state, submittedAt`. There
  is **no nested `comments` key** on a review element.
  `review_round_trips = len([r for r in reviews if r.state ==
  "CHANGES_REQUESTED"])` — free from this call.
- `comments` — **issue/timeline comments only.** Inline review-thread
  comments (the substantive review-friction signal) are NOT here
  (PR#13400: `comments` len 0, but 4 inline review comments exist).

**OQ1 resolved:** review-thread comments require a *second* call —
`gh api repos/{owner}/{repo}/pulls/{number}/comments` (count only).
Therefore:

```
review_comment_count = len(pr_view.comments)            # issue/timeline
                     + len(gh api .../pulls/<n>/comments) # inline review
```

This is **two `gh` invocations per unique PR ref**, not one. Still well
within budget (S2). The `--json` field list stays free-text-free; the
second endpoint is reduced to `length` and its bodies are never read.

**S2 — rate budget: PASS.** 5000/hr authenticated. Two calls per
*unique* PR (grouped, cached) over any realistic sync window is
negligible. No backoff/capping needed for v3.1.

**S3 — degraded paths: confirmed and enumerated.** The
`pulls/<n>/comments` endpoint returns HTTP 404 for numbers that are not
PRs (observed on issue numbers). Required branches, each → "field
absent, no exception, isolated to that PR":
- no `gh` / unauthenticated → skip friction pass entirely
- `pr view` fails (403/404/timeout) → all four fields absent for that PR
- `pr view` ok but comments API 404/403 → write
  `review_rounds`/`time_to_merge_s`/`review_decision`; leave
  `review_comment_count` absent (NOT 0 — unknown ≠ zero)

**OQ3 resolved:** merged-PR friction is immutable. Cache key for a PR
with `state == MERGED` is permanently valid (ignore TTL); only `open` /
`closed-unmerged` PRs honour the `_CACHE_TTL_HOURS` window.

**Net design change:** "one call per PR" → "≤2 calls per unique PR";
`parse_friction` takes two payloads (the `pr view` JSON and the
comments-endpoint length); `review_comment_count` is a sum and is the
one field that can be independently absent on a partial parse.

## Implementation notes (close-out, 2026-05-17)

Refinements made during implementation, consistent with the design's
intent but not pinned by it:

- **One combined `a` record per session**, not a separate friction
  amendment. Friction is computed once per unique `pr_ref` (per-sync
  `friction_memo`) and attached to each session's `ResolutionResult`,
  so the v3.0 pr_ref/pr_state and the v3.1 friction keys land in a
  single `a` line. The original `s` line is never mutated (v2.17),
  pinned by `test_friction_amendment_does_not_mutate_original_s_line`.
- **`_upsert_outcome` rewritten as `INSERT … ON CONFLICT(session_id)
  DO UPDATE … COALESCE(excluded.x, outcomes.x)`** for the four friction
  columns. Reason: a later friction-free write (manual `outcome
  attribute`, or a sync where `gh` was unavailable) must not wipe
  friction a prior sync enriched. v3.0 columns still overwrite.
- **Total `gh pr view` failure is not cached.** Phase-0 required
  fail-closed; the added refinement is that an all-None result from a
  primary-call failure is *not* written to `pr_cache`, so a transient
  outage retries next sync instead of poisoning a (possibly permanent,
  if merged) cache entry.
- **Friction surfaced through the shared `leverage.summarize`** (new
  `median_time_to_merge_s` / `median_review_comments` on
  `LeverageSummary`) so the web panel and TUI pane cannot diverge —
  same parity guarantee as v3.0's leverage rollup. `humanize_seconds`
  added there as the single duration formatter (report, both panels,
  invoice).
- **Test fixture drift fix:** `tests/test_outcome_sync.py::_mem_db()`
  now builds from `db._CREATE_SCHEMA_V1` instead of a hand-rolled
  `outcomes` table, so it can never again lag a schema migration.

No deviation from the privacy contract or the spec scenarios in
`specs/review-friction.md`.
