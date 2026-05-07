# Spec: Budget Limits

---

## Budget configuration loading

**WHEN** `load_budgets()` is called  
**AND** `~/.halyard/budgets.toml` does not exist  
**THEN** an empty dict is returned

**WHEN** `load_budgets()` is called  
**AND** `~/.halyard/budgets.toml` exists with valid entries  
**THEN** a dict keyed by project slug is returned  
**AND** each value is a `ProjectBudget` with the configured `daily_usd` and/or `monthly_usd`

**WHEN** `load_budgets()` is called  
**AND** `~/.halyard/budgets.toml` is present but corrupted  
**THEN** an empty dict is returned (silently ignored)

**WHEN** a project entry has only `monthly_usd`  
**THEN** `ProjectBudget.daily_usd` is `None`  
**AND** no daily limit is enforced for that project

---

## `check_budget()` — no limits configured

**WHEN** `check_budget()` is called for a project not in `~/.halyard/budgets.toml`  
**THEN** `None` is returned

**WHEN** `~/.halyard/budgets.toml` does not exist  
**THEN** `check_budget()` returns `None` for any project

---

## `check_budget()` — within limits

**WHEN** today's `billing=api` spend for the project is below `daily_usd`  
**AND** this month's `billing=api` spend is below `monthly_usd`  
**THEN** `check_budget()` returns `None`

---

## `check_budget()` — daily limit exceeded

**WHEN** today's `billing=api` spend for the project exceeds `daily_usd`  
**THEN** `check_budget()` returns a warning string  
**AND** the warning includes the project slug  
**AND** the warning includes the actual spend and the limit  
**AND** the warning includes "over daily limit"

---

## `check_budget()` — monthly limit exceeded

**WHEN** this month's `billing=api` spend for the project exceeds `monthly_usd`  
**THEN** `check_budget()` returns a warning string  
**AND** the warning includes the project slug  
**AND** the warning includes the actual monthly spend and the limit  
**AND** the warning includes "over monthly limit" (or equivalent)

---

## `check_budget()` — both limits exceeded

**WHEN** both daily and monthly limits are exceeded  
**THEN** a single warning string is returned  
**AND** both exceeded limits are mentioned in the same output

---

## Spend scope

**WHEN** computing spend for a budget check  
**THEN** only sessions with `billing=api` are counted  
**AND** sessions with `cost_usd == 0` are excluded  
**AND** sessions with `tokens_available=False` are excluded

**WHEN** a session has `billing=credits` or `billing=seat`  
**THEN** it is NOT counted toward the budget

---

## Hook integration — session start

**WHEN** `record_session_start()` is called  
**AND** the session file already exists  
**THEN** the budget check is skipped (idempotent guard)

**WHEN** `record_session_start()` is called  
**AND** no active project is found  
**THEN** the budget check is skipped

**WHEN** `record_session_start()` is called  
**AND** an active project is found  
**BUT** no project directory can be located  
**THEN** the budget check is skipped

**WHEN** `record_session_start()` fires and a budget limit is exceeded  
**THEN** the warning is printed to stdout  
**AND** the session file is written and the session proceeds normally  
(the warning is informational, never blocking)

---

## `halyard budget` command

**WHEN** `halyard budget` is run  
**AND** `~/.halyard/budgets.toml` does not exist  
**THEN** a helpful message is shown explaining how to create a budget file  
**AND** exits with code 0

**WHEN** `halyard budget` is run  
**AND** budgets are configured  
**THEN** each project is listed with today's spend vs daily limit (if set)  
**AND** each project is listed with this month's spend vs monthly limit (if set)  
**AND** over-limit entries are marked with ⚠  
**AND** exits with code 0

**WHEN** a project has no daily limit configured  
**THEN** the today line shows "(no limit)"

---

## `halyard set-budget` command

**WHEN** `halyard set-budget <slug> --daily <n>` is run  
**THEN** the daily limit for that project is written to `~/.halyard/budgets.toml`  
**AND** the monthly limit (if any) is preserved  
**AND** confirmation is printed

**WHEN** `halyard set-budget <slug> --monthly <n>` is run  
**THEN** the monthly limit is written  
**AND** the daily limit (if any) is preserved

**WHEN** `~/.halyard/budgets.toml` does not exist  
**AND** `halyard set-budget` is run  
**THEN** the file is created

**WHEN** `halyard set-budget` is run without `--daily` or `--monthly`  
**THEN** an error is shown and no file is written
