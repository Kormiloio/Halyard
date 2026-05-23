# Tasks

Implementation checklist for v3.0 — Outcome Graph.

## 0. Prerequisites

- [x] 0.1 v2.16 shipped (security baseline).
- [x] 0.2 v2.17 shipped (correction records, locking).
- [x] 0.3 v2.18 shipped (project registry, migrations, content-addressed
  cache).

## 1. Schema and amendment keys

- [x] 1.1 Define new `a` record keys: `pr_ref`, `pr_state`, `branch`,
  `commit_count`, `code_added`, `code_removed`, `outcome_resolved_at`.
  — Shipped in v2.24-outcome-metadata.
- [x] 1.2 Update `AiSession` to expose outcome fields.
  — Shipped in v2.24-outcome-metadata.
- [x] 1.3 Migration: add `outcomes` and `pr_cache` tables to SQLite cache.
  — Shipped in v2.18-cache-and-audit-hardening (db.py v2 → v3 migration).

## 2. Signal collectors

- [x] 2.1 `git_outcome.py` — commit / churn / branch detection.
  — Already populated at capture time by Claude Code / Cursor / Gemini
  collectors via halyard.git_context (commits_in_window, current_branch,
  numstat_summary). A standalone backfill module was unnecessary.
- [x] 2.2 `gh_outcome.py` — PR linkage and state via `gh` CLI.
  — Implemented as `halyard.outcomes` (gh_available,
  fetch_prs_for_branch, resolve_sessions). 41 tests in
  test_outcome_sync.py.
- [x] 2.3 `shell_history.py` — test-run detection (hashed commands).
  — New module. Privacy-hardened: only counts canonical test commands
  (pytest, npm test, go test, etc.); never returns or stores raw lines;
  off by default behind `[outcomes].shell_history = false`. Covered by
  tests/test_shell_history.py.
- [x] 2.4 `attempt_tracker.py` — branch-pattern repeated-attempt
  heuristic.
  — New module. Collapses common iteration suffixes (-v2, -take2,
  -rebased, -retry, etc.) onto a single logical branch. Tests in
  tests/test_attempt_tracker.py.

## 3. CLI surface

- [x] 3.1 `halyard outcome sync [--since=<date>]`.
- [x] 3.2 `halyard outcome report [--project=<slug>] [--since=<date>]`.
- [x] 3.3 `halyard outcome attribute <session-id> <pr-ref>` (manual
  override).
- [x] 3.4 Feature flag `outcomes.enabled` in `halyard.toml`.
  — `halyard.outcomes_config` reads `[outcomes]` table; both
  `halyard outcome sync` and `halyard outcome report` honour the flag
  and exit cleanly when disabled.

## 4. Surfaces

- [x] 4.1 Dashboard "Leverage" panel.
  — `_leverage_panel()` in dashboard.py renders a 30-day rollup: %
  merged, count buckets per pr_state, "halyard outcome sync" hint when
  unresolved sessions exist. CSS in the same file.
- [x] 4.2 TUI session detail outcomes section.
  — Added an outcome glyph badge to the SessionFeed line: `✓ owner/repo#42`
  for merged, `•` for open, `✗` for closed, `—` for none. One-line
  layout preserved.
- [x] 4.3 Invoice evidence appendix PR refs.
  — `_render_pr_refs_subsection()` adds a "Linked engineering artifacts"
  subsection to the AI evidence appendix listing every PR a session
  linked to with its state and session count. No prompts/diffs/code.

## 5. Privacy contract

- [x] 5.1 Fuzz test: no source-code or prompt-text leakage.
  — `tests/test_outcomes_privacy_fuzz.py` seeds random sensitive
  markers into note/resume_command, runs every rendering surface, and
  asserts none of the markers appears in the output. 5 parametrized
  trials.
- [x] 5.2 Documented threat model in `specs/privacy-contract.md`.
  — Pin-by-pin contract: integer-only / enum-only collector outputs,
  opt-out flag, shell-history opt-in, fail-closed on permission errors.
- [x] 5.3 `outcomes.enabled = false` cleanly disables all collection.
  — Both `halyard outcome sync` and `halyard outcome report` check the
  flag before doing any work; tests pin the default-on / explicit-off
  behaviour.

## 6. Tests

- [x] 6.1 Signal extraction: 5+ tests per collector.
  — outcomes (41 tests), attempt_tracker (6), shell_history (12),
  outcomes_config (6), leverage_panel (6).
- [x] 6.2 PR resolution edge cases (no `gh`, no repo, detached HEAD,
  squash-merge, force-push).
  — Covered in tests/test_outcome_sync.py (pre-existing 41 tests).
- [x] 6.3 Outcome report buckets correctly under each combination.
  — Covered in tests/test_outcome_sync.py.
- [x] 6.4 Privacy contract fuzz test green.
  — tests/test_outcomes_privacy_fuzz.py — green across 5 trials.

## 7. Design partner

- [ ] 7.1 Recruit one engineering team to run v3.0 dark-mode for 2
  weeks.
  — User task. Tracked in v0-time-and-invoice §6 / OSS launch
  checklist; v3.0 itself ships green without this gate.
- [ ] 7.2 Collect feedback on signal accuracy and surface usefulness.
  — User task.
- [ ] 7.3 Public write-up co-authored with the design partner.
  — User task.
