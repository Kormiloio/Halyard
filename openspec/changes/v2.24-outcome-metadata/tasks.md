# Tasks: v2.24 — Outcome Metadata Uplift

Read `proposal.md` and `specs/` before starting. Check each item off as it
ships. Do not mark complete until tests pass.

**Prerequisite:** v2.18 must be merged before tasks in Section 4.

---

## Section 1 — AiSession data model

- [ ] Add `branch: str | None = None` to `AiSession` dataclass (`ai_log.py`)
- [ ] Add `commit_count: int | None = None` to `AiSession`
- [ ] Add `code_removed: int | None = None` to `AiSession` (complements
  existing `code_added`)
- [ ] Add `pr_ref: str | None = None` to `AiSession`
- [ ] Add `pr_state: str | None = None` to `AiSession`
- [ ] Add `outcome_resolved_at: str | None = None` to `AiSession`
- [ ] Update `to_log_line()` to serialize all new fields as key=value pairs
- [ ] Update `parse_sessions()` KV dispatch to read all new fields
- [ ] Update `parse_sessions()` to promote legacy `branch:<name>` tags to the
  `branch` field on read (backward-compat migration)
- [ ] Add `pr_ref` and `pr_state` to `Amendment.allowed_keys`

## Section 2 — git_context.py new functions

- [ ] Add `commits_in_window(cwd, start, end) -> int | None`
  - Runs `git log --since --until --oneline`, counts lines
  - 2-second timeout; returns `None` on any error
  - Tests: normal repo, no git, timeout, empty window, window with commits
- [ ] Add `head_sha(cwd) -> str | None`
  - Returns 12-char short SHA of HEAD, or None
  - 2-second timeout; returns `None` on any error
  - Tests: normal repo, no git, detached HEAD

## Section 3 — Collector updates (all four)

- [ ] **Claude Code collector:** set `session.branch` from `current_branch()`
  (remove `tags` append); set `session.commit_count` from `commits_in_window()`
- [ ] **Claude Code collector:** capture `sha_at_start` at session open; compute
  `code_added` / `code_removed` from numstat at stop
- [ ] **Cursor collector:** same branch + commit_count changes as Claude Code
- [ ] **Cursor collector:** sha_at_start + numstat code delta at stop
- [ ] **Codex collector:** branch + commit_count changes
- [ ] **Codex collector:** sha_at_start + numstat code delta
- [ ] **Gemini CLI collector:** branch field promotion only (already has code
  delta from history file — do not replace with numstat)
- [ ] Confirm all four collectors pass existing tests after changes

## Section 4 — SQLite migrations (requires v2.18)

- [ ] Write migration v1 → v2 in `db.py`: add new columns to `sessions` table
- [ ] Create `outcomes` table in migration v2
- [ ] Create `pr_cache` table in migration v2
- [ ] `halyard db reset` message updated to mention branch field migration

## Section 5 — `halyard outcome` CLI sub-app

- [ ] Create `src/halyard/outcomes.py` module with resolution logic
- [ ] `halyard outcome sync` command (flags: `--since`, `--project`, `--dry-run`,
  `--force`)
- [ ] `halyard outcome report` command (flags: `--since`, `--project`)
- [ ] `halyard outcome attribute SESSION_ID PR_REF` command
- [ ] Register `outcome_app` in `cli.py`
- [ ] Gate all `gh` calls — absent `gh` prints warning and exits cleanly

## Section 6 — Reports and TUI display

- [ ] `halyard report` shows `branch` and `commit_count` per session when
  present (no layout break when absent)
- [ ] `halyard tui` session feed shows branch when present
- [ ] Outcome bucket totals visible in `halyard report --outcomes`

## Section 7 — Tests

- [ ] `tests/test_outcome_metadata.py` — AiSession field serialization /
  parsing, tag migration, amendment record folding for new fields
- [ ] `tests/test_git_context_v2.py` — `commits_in_window`, `head_sha`,
  edge cases (no repo, timeout, detached HEAD)
- [ ] `tests/test_collectors_outcome.py` — branch field, commit_count, and
  numstat code delta for Claude/Cursor/Codex collectors (monkeypatched git)
- [ ] `tests/test_outcome_sync.py` — resolution algorithm, pr_cache TTL,
  dry-run mode, `gh` absent graceful exit, `outcome attribute` command
- [ ] `tests/test_outcome_report.py` — outcome-bucketed output, trust labels,
  "not synced" display

## Section 8 — Docs sync

- [ ] Update `docs/PRD-halyard.md` — mark v2.24 active, update product ladder
- [ ] Update `docs/current-direction.md` — move v2.24 from "after launch" to
  "active" once OSS launch gate passes
- [ ] Update `openspec/project.md` — move v2.24 from focus item 3 to 1 once
  v2.18 ships
- [ ] Update `README.md` — once shipped, move outcome metadata from "Next" to
  "Current"
