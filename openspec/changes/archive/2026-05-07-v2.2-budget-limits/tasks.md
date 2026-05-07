# Tasks: v2.2 — Budget Limits

## Spec & design
- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/budget-limits.md

## `src/halyard/budget.py` (new module)
- [x] Define `ProjectBudget` dataclass (`daily_usd: float | None`, `monthly_usd: float | None`)
- [x] Define `BudgetStatus` dataclass (project slug, today_spend, today_limit, month_spend, month_limit)
- [x] Implement `load_budgets() -> dict[str, ProjectBudget]`
  - Reads `~/.halyard/budgets.toml`; returns empty dict if absent or corrupted
- [x] Implement `check_budget(project_slug, project_dir, now=None) -> str | None`
  - Load budgets; return None if no entry for slug
  - Parse `project_dir / ai-sessions.log`
  - Filter: `billing=api`, `cost_usd > 0`, `tokens_available=True`
  - Sum daily and monthly spend
  - Return warning string if either limit exceeded, else None
- [x] Implement `budget_status(now=None) -> list[BudgetStatus]`
  - Uses hub log when available (filters by project=slug); else CWD project dir
  - Returns spend-vs-limit for each configured project
- [x] Implement `set_budget(slug, daily_usd, monthly_usd) -> ProjectBudget`
  - Atomic read-modify-write of `~/.halyard/budgets.toml`

## Hook integration
- [x] Wire budget check into `record_session_start()` in `src/halyard/collectors/claude_code.py`
  - Skip if session file already exists (idempotent guard)
  - Skip if no active project
  - Skip if no project directory found
  - Print warning to stdout if `check_budget()` returns non-None
- [x] Wire same pattern into `src/halyard/collectors/cursor.py`
- [x] Wire same pattern into `src/halyard/collectors/gemini_cli.py`

## `src/halyard/cli.py` — new commands

### `halyard budget`
- [x] Add `budget` command
  - If no `budgets.toml`: print helpful message explaining how to create one, exit 0
  - Call `budget_status()`, render table with spend vs limits
  - Mark over-limit rows with ⚠
  - Exit code 0 always

### `halyard set-budget`
- [x] Add `set-budget <slug> --daily <n> --monthly <n>` command
  - At least one of `--daily` / `--monthly` required; error if neither provided
  - Read existing file (or start fresh), update/add entry for slug
  - Write file, print confirmation
  - Preserve existing limits not being updated

## Tests (`tests/test_budget.py`)
- [x] `test_load_budgets_absent` — returns empty dict
- [x] `test_load_budgets_valid` — parses both daily and monthly limits
- [x] `test_load_budgets_monthly_only` — daily_usd is None
- [x] `test_load_budgets_corrupted` — returns empty dict
- [x] `test_check_budget_no_entry` — returns None
- [x] `test_check_budget_within_limits` — returns None
- [x] `test_check_budget_daily_exceeded` — warning contains slug, actual spend, limit
- [x] `test_check_budget_monthly_exceeded` — warning contains monthly info
- [x] `test_check_budget_both_exceeded` — single warning with both limits
- [x] `test_check_budget_excludes_credits_sessions` — billing=credits not counted
- [x] `test_check_budget_excludes_seat_sessions` — billing=seat not counted
- [x] `test_check_budget_excludes_zero_cost` — cost_usd=0 not counted
- [x] `test_set_budget_creates_file` — creates budgets.toml
- [x] `test_set_budget_updates_existing` — updates daily, preserves monthly
- [x] `test_set_budget_preserves_other_entries` — other slugs untouched

## Quality
- [x] Run full test suite — all passing (202 tests)
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
