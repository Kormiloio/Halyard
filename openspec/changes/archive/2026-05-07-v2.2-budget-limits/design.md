# Design: Budget Limits

## Config file: `~/.halyard/budgets.toml`

```toml
["acme:auth-migration"]
daily_usd   = 50.00
monthly_usd = 500.00

["globex:reporting"]
monthly_usd = 200.00
```

Keyed by project slug. Both `daily_usd` and `monthly_usd` are optional.
An absent file or absent key for a project means no limit for that dimension.

---

## New module: `src/halyard/budget.py`

```python
_BUDGETS_FILE = Path.home() / ".halyard" / "budgets.toml"

@dataclass
class ProjectBudget:
    daily_usd: float | None = None
    monthly_usd: float | None = None

def load_budgets() -> dict[str, ProjectBudget]:
    """Read ~/.halyard/budgets.toml. Returns empty dict if absent."""

def check_budget(
    project_slug: str,
    project_dir: Path,
    now: datetime | None = None,
) -> str | None:
    """Return a warning string if any limit is exceeded, else None."""

def budget_status(now: datetime | None = None) -> list[BudgetStatus]:
    """Return spend-vs-limit for all configured projects (for halyard budget)."""
```

### `check_budget()` logic

1. Load budgets. If no entry for `project_slug`, return `None`.
2. Parse sessions from `project_dir / ai-sessions.log`.
3. Filter to `billing=api` sessions with `cost_usd > 0`.
4. Sum `cost_usd` for today (`start.date() == now.date()`).
5. Sum `cost_usd` for this month (`start.year == now.year and start.month == now.month`).
6. Compare against limits. Build a warning string if either is exceeded.
7. Return the warning string, or `None` if within limits.

Example warning output (written to stdout by the hook):

```
⚠  Halyard budget: acme:auth-migration  today $52.30 / $50.00  ⚠ over daily limit
   Session will proceed. Run `halyard budget` to review.
```

If both limits are exceeded:
```
⚠  Halyard budget: acme:auth-migration  today $52.30 / $50.00  monthly $510.00 / $500.00
   Session will proceed. Run `halyard budget` to review.
```

---

## Hook integration

The budget check runs in `record_session_start()` for each collector. The
check is skipped if:
- No active project (no timer running, no active slug).
- The session file already exists (idempotent guard — check fires once per
  session, not once per prompt).

```python
def record_session_start() -> int:
    if _CC_SESSION_FILE.exists():
        return 0  # already tracking — budget already checked

    # Budget check fires here, before writing the session file
    active = _read_active_project()
    if active:
        project_dir = find_project_dir() or find_hub()
        if project_dir:
            warning = check_budget(active, project_dir)
            if warning:
                print(warning)

    _CC_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CC_SESSION_FILE.write_text(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    return 0
```

Claude Code, Cursor, and Gemini CLI all have a session-start hook entry point.
The same pattern applies to all three. The warning is printed to stdout, which
each tool surfaces in the user's terminal.

---

## `halyard budget` command

Shows all projects that have budget entries, with current spend and status.
Reads `~/.halyard/budgets.toml`, then for each project finds its log via
`find_project_dir()` or falls back to the hub.

```
$ halyard budget

Budget status — May 2026
────────────────────────────────────────────────────
  acme:auth-migration
    Today      $52.30 / $50.00   ⚠ over
    This month $312.00 / $500.00  ✓ 62% used

  globex:reporting
    Today      (no limit)
    This month $41.20 / $200.00   ✓ 21% used
────────────────────────────────────────────────────
```

Exit code 0 always (informational command). If no `budgets.toml` exists, show
a helpful message explaining how to create one.

---

## `halyard set-budget` command

A convenience command to add or update a budget entry without editing TOML
directly:

```
$ halyard set-budget acme:auth-migration --daily 50 --monthly 500
Budget set for acme:auth-migration: daily $50.00  monthly $500.00
```

Either flag is optional. Running it with only `--daily` updates just the daily
limit, leaving the monthly untouched.

---

## Scope of "spend" in budget check

Only sessions where:
- `billing == "api"` (or absent, which defaults to `"api"`)
- `cost_usd > 0`
- `tokens_available == True`

Excluded:
- `billing=credits` (Cursor, Codex) — no per-session API cost
- `billing=seat` — flat plan, no per-session cost
- Sessions with `cost_usd == 0` and `tokens_available=False` — unknown model,
  cost not calculable

This is the conservative, accurate interpretation. A user's Cursor usage does
not count against their API budget.

---

## Performance

`check_budget()` parses the full `ai-sessions.log` on every session start.
For a one-year log (~5,000 lines), this is under 10ms — within the 100ms
target specified in the proposal. If logs grow significantly larger, a future
optimisation could scan from the end of the file (monthly data is always
recent), but that complexity is not warranted now.

---

## What does NOT change

- `ai-sessions.log` format. No new fields, no changes to existing records.
- `halyard.toml`. Budget config lives entirely in `~/.halyard/budgets.toml`.
- Default behaviour for projects with no budget entry — no warnings, no
  changes.
