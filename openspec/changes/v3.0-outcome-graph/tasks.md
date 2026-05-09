# Tasks

Implementation checklist for v3.0 — Outcome Graph. Detailed task list
deferred until design.md lands; this is the high-level outline.

## 0. Prerequisites

- [ ] 0.1 v2.16 shipped (security baseline).
- [ ] 0.2 v2.17 shipped (correction records, locking).
- [ ] 0.3 v2.18 shipped (project registry, migrations, content-addressed
  cache).

## 1. Schema and amendment keys

- [ ] 1.1 Define new `a` record keys: `pr_ref`, `pr_state`, `branch`,
  `commit_count`, `code_added`, `code_removed`, `outcome_resolved_at`.
- [ ] 1.2 Update `AiSession` to expose outcome fields.
- [ ] 1.3 Migration: add `outcomes` and `pr_cache` tables to SQLite cache.

## 2. Signal collectors

- [ ] 2.1 `git_outcome.py` — commit / churn / branch detection.
- [ ] 2.2 `gh_outcome.py` — PR linkage and state via `gh` CLI.
- [ ] 2.3 `shell_history.py` — test-run detection (hashed commands).
- [ ] 2.4 `attempt_tracker.py` — branch-pattern repeated-attempt
  heuristic.

## 3. CLI surface

- [ ] 3.1 `halyard outcome sync [--since=<date>]`.
- [ ] 3.2 `halyard outcome report [--project=<slug>] [--since=<date>]`.
- [ ] 3.3 `halyard outcome attribute <session-id> <pr-ref>` (manual
  override).
- [ ] 3.4 Feature flag `outcomes.enabled` in `halyard.toml`.

## 4. Surfaces

- [ ] 4.1 Dashboard "Leverage" panel.
- [ ] 4.2 TUI session detail outcomes section.
- [ ] 4.3 Invoice evidence appendix PR refs.

## 5. Privacy contract

- [ ] 5.1 Fuzz test: no source-code or prompt-text leakage.
- [ ] 5.2 Documented threat model in `specs/privacy-contract.md`.
- [ ] 5.3 `outcomes.enabled = false` cleanly disables all collection.

## 6. Tests

- [ ] 6.1 Signal extraction: 5+ tests per collector.
- [ ] 6.2 PR resolution edge cases (no `gh`, no repo, detached HEAD,
  squash-merge, force-push).
- [ ] 6.3 Outcome report buckets correctly under each combination.
- [ ] 6.4 Privacy contract fuzz test green.

## 7. Design partner

- [ ] 7.1 Recruit one engineering team to run v3.0 dark-mode for 2
  weeks.
- [ ] 7.2 Collect feedback on signal accuracy and surface usefulness.
- [ ] 7.3 Public write-up co-authored with the design partner.
