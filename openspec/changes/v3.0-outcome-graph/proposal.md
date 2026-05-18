# Proposal: v3.0 — Outcome Graph

## Why

Halyard today shows that AI work happened — sessions, tokens, cost. It
cannot show whether that AI work produced engineering progress. The
investor pressure test (`strategy/investor-pressure-test.md`) names this
gap as the difference between "prettier vendor dashboard" (a trap) and
"neutral system of record for AI-assisted work" (the company).

The CTO question Halyard cannot answer today:

> Is the AI spend producing engineering leverage?

v3.0 makes that answer possible by tying each AI session to engineering
artifacts (commits, branches, PRs, tests) and surfacing the linkage in
dashboards, reports, and the invoice evidence appendix.

This is the strategic anchor of the next quarter of work. The full PRD
is in `strategy/prd-outcome-graph.md`.

## What changes

Seven outcome signals captured at session-close or via `halyard outcome
sync`:

1. Git commits in session window.
2. Code churn (lines added/removed).
3. Branch context.
4. PR linkage (branch matches `gh pr list` head).
5. PR outcome (merged / closed-unmerged / open / none).
6. Test runs in window (from shell history, hashed).
7. Repeated attempts on the same ticket.

Surfaces:

- New `halyard outcome sync` and `halyard outcome report` commands.
- New SQLite `outcomes` and `pr_cache` tables (via v2.18 migration
  framework).
- Dashboard "Leverage" panel: percent of recent AI sessions landing in
  merged PRs.
- Invoice evidence appendix gains PR refs.
- TUI session detail panel adds an outcomes section.

Data shape:

- All outcome data flows through `a` correction records (v2.17).
- New amendment keys: `pr_ref`, `pr_state`, `branch`, `commit_count`,
  `code_added`, `code_removed`, `outcome_resolved_at`.
- Trust labels on each signal: `captured` (git/gh-derived), `calculated`
  (numstat sums), `inferred` (shell history matches).

## What stays the same

- Plain-text log is still the source of truth.
- No prompt or source-code capture. Hashed file paths only when used for
  cross-developer signals.
- Local-first: `gh` and `git` commands run on the user's machine with
  their credentials. Halyard does not phone home.
- A user can disable outcome collection with one flag
  (`outcomes.enabled = false` in `halyard.toml`).
- `s` line format unchanged.

## Out of scope

- Tool errors / approval rejections (v3.1 — needs collector enhancement).
- MCP server inventory (v3.1).
- Review friction signals — PR review-comment count, time-to-merge
  (v3.1, needs GitHub API).
- User disagreement signals (collector-specific, deferred).
- Hosted dashboards (v3.4+).
- LLM-based "good vs. bad" judgment of work. Halyard surfaces signals;
  humans interpret.

## Prerequisites

v2.16, v2.17, and v2.18 must ship first. Specifically:

- v2.16 — secure dashboard so outcomes surface there safely.
- v2.17 — correction records, so outcome data is a clean amendment, not
  a log mutation.
- v2.18 — schema migrations, so outcomes table can land without a
  destructive `db reset`.

## Success criteria

1. On a real project with `git` and `gh` installed, `halyard outcome
   sync` resolves at least 80% of recent sessions to a branch and 60% to
   a PR.
2. The dashboard "Leverage" panel renders within the 10-second refresh
   budget on a 100k-line log.
3. Privacy contract: a fuzz test confirms no source code or prompt text
   leaks into the log, the cache, or the redacted egress (v3.3
   prerequisite).
4. Test suite gains at least 30 new tests covering signal extraction, PR
   resolution edge cases, and the `outcome` reports.
5. One real engineering team uses Halyard with v3.0 for two weeks and
   produces a write-up of "what we learned about our AI usage." That
   artifact becomes the public demo.

## Strategic implication

v3.0 is the first version where the elevator pitch lands without
asterisks:

> Halyard instruments AI-assisted engineering work where it happens —
> across all tools — and shows whether the work is producing leverage,
> without capturing prompts or source code by default.

Until v3.0, "leverage" is a future tense. v3.0 makes it present tense.

## Detailed design

No standalone `design.md` was written for v3.0. The design was realized
incrementally and each carrying changeset holds its own design notes:

- Schema + amendment keys — v2.18 (migration framework), v2.24 (outcome
  metadata fields on `AiSession`, `outcomes`/`pr_cache` tables).
- Signal collectors — `halyard.outcomes` (gh PR linkage),
  `git_context` (commits/churn/branch at capture time), `shell_history`
  (opt-in hashed test-run detection), `attempt_tracker` (branch-pattern
  repeat heuristic).
- Surfaces — Leverage panel with web+TUI parity (v2.70), invoice PR-ref
  appendix, `halyard outcome sync/report/attribute`.

`strategy/prd-outcome-graph.md` remains the full PRD.

## Status (reconciled 2026-05-17)

Code-complete. Tasks §1–§6 are done; §7 (design-partner dark-mode run,
feedback, public write-up) is a user/GTM gate and the changeset ships
green without it. 1286 tests passing repo-wide; the v3.0-specific
suites (`test_outcome_sync`, `test_shell_history`,
`test_attempt_tracker`, `test_outcomes_config`, `test_leverage_panel`,
`test_outcomes_privacy_fuzz`) are green. The roadmap entry and the
"Deferred or gated" note in `openspec/project.md` were corrected to
reflect code-complete-but-GTM-gated rather than unbuilt. The next
engineering increment is v3.1 — review-friction signals
(`openspec/changes/v3.1-review-friction/`).
