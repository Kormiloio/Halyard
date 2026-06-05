# v5.16 — Untrusted-input hardening

## Why

The pre-open-source-release audit (`docs/reviews/2026-06-pre-release-audit.md`)
found that every untrusted-input parser in Halyard admits values that crash
aggregation, corrupt billing, or enable arbitrary file write. Halyard reads
attacker-influenceable files (its own `ai-sessions.log`, collector state
files, AI-tool history) and arguments, and a single poisoned input can take
down the dashboard, TUI, MCP server, and every report machine-wide. These are
release blockers — the tool is about to run on many strangers' machines.

This changeset closes the input-validation blockers (audit IDs in brackets):

- **B1** — `ai_log.py` admits non-finite cost/credits floats (`inf`/`nan`)
  because the guard checks only `< 0`. `inf` raises an uncaught
  `decimal.InvalidOperation` in `usage.sum_spend`; `nan` silently poisons
  every total to `NaN`. One poisoned line in any aggregated log crashes or
  corrupts every consumer.
- **B7** — `windsurf.py` builds a state-file path from an unsanitized stdin
  `trajectory_id`, allowing `../` traversal to overwrite arbitrary
  user-writable files (e.g. `~/.claude/settings.json` → code execution).
- **B8** — collector parsers (`gemini_history.py`, `codex_app.py`,
  `copilot.py`) coerce token fields with bare `int()`/`fromtimestamp`
  outside any try/except; one malformed file aborts an entire `import-*`
  run, silently skipping every later session.
- **B9** — `git_context.py` (and sibling git-ref call sites) build
  `git diff <sha> HEAD` with no `--` separator and no hex validation, so an
  attacker-controlled `sha_at_start` like `--output=<path>` injects a git
  option that writes to an arbitrary file.
- **B10** — `outcomes.py` interpolates an unvalidated `repo` into
  `gh api repos/{repo}/...` (endpoint injection / traversal) and writes
  amendment fields without `_safe_field` (log injection).
- **B19** — `leverage_pane.py` renders attacker-controlled
  `mcp_server_names` into the TUI without `rich.markup.escape`, so a crafted
  value raises `MarkupError` and crashes the dashboard on every refresh.

## What changes

Validate or sanitize each untrusted value at the point it enters Halyard:

- **B1:** reject non-finite floats at the parse choke points in `ai_log.py`
  (positional `cost_usd` and the `FLOAT_4` `credits` handler), and add a
  defensive `math.isfinite` skip in `usage.sum_spend` (the aggregation choke
  point) so a non-finite arriving via the SQLite cache or direct construction
  degrades to a skipped value instead of a crash.
- **B7:** sanitize `trajectory_id` to a safe slug and assert the resolved
  state-file path stays inside the intended `ws-sessions/` directory.
- **B8:** wrap per-file collector parsing in a guard that honors the
  documented "return None on error" contract for
  `ValueError`/`TypeError`/`OverflowError`/`OSError`, and guard the importer
  loops so one bad file skips rather than aborts the batch.
- **B9:** insert a literal `--` before user-influenced git refs and reject
  any ref not matching `^[0-9a-fA-F]{4,40}$`, at every git-ref call site.
- **B10:** validate `repo` against `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`
  (rejecting `..`) before any `gh` call; route amendment field writes through
  the existing `_safe_field` path.
- **B19:** `rich.markup.escape` the rendered MCP phrase and/or re-apply the
  MCP allowlist in `summarize_mcp`.

## Out of scope

- Localhost HTTP auth and secret-file hardening (B2/B3/B4/B5/B13) — these are
  v5.19.
- Billing/aggregation correctness (B14–B17, B11, B12, B20) — v5.17.
- Robustness/data-loss (B6, B18, B21) — v5.18.
- The extreme-integer DoS on token counts: Python 3.11+'s 4300-digit
  `int()` string limit already rejects the pathological case at the runtime
  level (verified), so no code change is required here; noted for the record.

## Success criteria

- A poisoned `ai-sessions.log` line with `inf`/`nan` cost no longer creates a
  session, and no consumer crashes or returns `NaN`.
- A malicious `trajectory_id`/git-ref/`repo`/`mcp_server_names` value cannot
  escape its intended path, inject a git/gh option, or crash the TUI.
- A single malformed collector file skips with a warning instead of aborting
  the import.
- Full suite green; ruff + mypy clean. Each fix has a regression test.
