# Tasks: v2.24 — Outcome Metadata Uplift

Read `proposal.md` and `specs/` before starting. Check each item off as it
ships. Do not mark complete until tests pass.

**Prerequisite:** v2.18 must be merged before tasks in Section 4.

---

## Section 1 — AiSession data model

- [x] Add `branch: str | None = None` to `AiSession` dataclass (`ai_log.py`)
- [x] Add `commit_count: int | None = None` to `AiSession`
- [x] Add `code_removed: int | None = None` to `AiSession` (complements
  existing `code_added`)
- [x] Add `pr_ref: str | None = None` to `AiSession`
- [x] Add `pr_state: str | None = None` to `AiSession`
- [x] Add `outcome_resolved_at: str | None = None` to `AiSession`
- [x] Update `to_log_line()` to serialize all new fields as key=value pairs
- [x] Update `parse_sessions()` KV dispatch to read all new fields
- [x] Update `parse_sessions()` to promote legacy `branch:<name>` tags to the
  `branch` field on read (backward-compat migration)
- [x] Add `pr_ref` and `pr_state` to `Amendment.allowed_keys`

## Section 2 — git_context.py new functions

- [x] Add `commits_in_window(cwd, start, end) -> int | None`
  - Runs `git log --since --until --oneline`, counts lines
  - 2-second timeout; returns `None` on any error
  - Tests: normal repo, no git, timeout, empty window, window with commits
- [x] Add `head_sha(cwd) -> str | None`
  - Returns 12-char short SHA of HEAD, or None
  - 2-second timeout; returns `None` on any error
  - Tests: normal repo, no git, detached HEAD

## Section 3 — Collector updates (all four)

- [x] **Claude Code collector:** set `session.branch` from `current_branch()`
  (remove `tags` append); set `session.commit_count` from `commits_in_window()`
- [x] **Claude Code collector:** capture `sha_at_start` at session open; compute
  `code_added` / `code_removed` from numstat at stop
- [x] **Cursor collector:** same branch + commit_count changes as Claude Code
- [x] **Cursor collector:** sha_at_start + numstat code delta at stop
- [x] **Codex collector:** branch + commit_count changes
- [x] **Codex collector:** sha_at_start + numstat code delta — intentionally
  omitted; Codex is pull-based (no open hook), so sha_at_start is not capturable
- [x] **Gemini CLI collector:** branch field promotion only (already has code
  delta from history file — do not replace with numstat)
- [x] Confirm all four collectors pass existing tests after changes

## Section 4 — SQLite migrations (requires v2.18)

- [x] Write migration v2 → v3 in `db.py`: add new columns to `sessions` table
- [x] Create `outcomes` table in migration v3
- [x] Create `pr_cache` table in migration v3
- [x] `halyard db reset` message updated to mention branch field migration

## Section 5 — `halyard outcome` CLI sub-app

- [x] Create `src/halyard/outcomes.py` module with resolution logic
- [x] `halyard outcome sync` command (flags: `--since`, `--project`, `--dry-run`,
  `--force`)
- [x] `halyard outcome report` command (flags: `--since`, `--project`)
- [x] `halyard outcome attribute SESSION_ID PR_REF` command
- [x] Register `outcome_app` in `cli.py`
- [x] Gate all `gh` calls — absent `gh` prints warning and exits cleanly

## Section 6 — Reports and TUI display

- [x] `halyard report` shows `branch` and `commit_count` per session when
  present — shown as a "By branch" section with commit + line totals
- [x] `halyard tui` session feed shows branch when present (appended as `[branch]`)
- [x] Outcome bucket totals visible in `halyard report --outcomes`

## Section 7 — Tests

- [x] `tests/test_outcome_metadata.py` — AiSession field serialization /
  parsing, tag migration, amendment record folding for new fields
- [x] `tests/test_git_context_v2.py` — `commits_in_window`, `head_sha`,
  edge cases (no repo, timeout, detached HEAD)
- [x] `tests/test_collectors_outcome.py` — branch field, commit_count, and
  numstat code delta for Claude/Cursor collectors (monkeypatched git)
- [x] `tests/test_outcome_sync.py` — resolution algorithm, pr_cache TTL,
  dry-run mode, `gh` absent graceful exit, `outcome report` bucketing
- [x] `tests/test_outcome_report.py` — merged into `test_outcome_sync.py`

## Section 8 — Docs sync

- [x] Update `docs/PRD-halyard.md` — mark v2.24 active, update product ladder
- [x] Update `docs/current-direction.md` — v2.24 is active
- [x] Update `openspec/project.md` — v2.24 focus item updated
- [x] Update `README.md` — once shipped, move outcome metadata from "Next" to
  "Current"
