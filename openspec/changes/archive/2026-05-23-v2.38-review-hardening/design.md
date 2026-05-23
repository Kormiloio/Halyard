# v2.38 — Review Hardening: Design

## Money: float → Decimal

`pricing.calculate_cost()` converts token counts and rates to `Decimal`,
computes, then quantizes to 4 places with `ROUND_HALF_UP` before returning a
`float` (the public return type is unchanged so callers/serialization are
untouched). Invoice/voyage amounts (`invoicing`, `voyages`) quantize to 2
places with `ROUND_HALF_UP` instead of banker's `round()`.

Trade-off: keeping the `float` return type avoids a Pydantic/serialization
ripple. The Decimal work is internal to the computation; only the rounded
value crosses the boundary. Existing golden values may shift by ≤1 unit in
the last place — tests are updated to the deterministic value.

## Unified spend

New `usage.sum_spend(sessions, *, period_start, period_end, api_only)` is the
single window+filter implementation. Window is **half-open on session end**
(`period_start <= s.end < period_end`) — the invoicing convention, chosen
because billing keys off when work completed. `budget`, `invoicing`, and the
ledger's direct-cost path call it. Documented divergence (seat/allocated plan
cost) stays separate but is labelled.

## Pricing cache

Multipliers fold into `_merged_table` so base rates and multipliers invalidate
together in `update_pricing()`. `_load_local_toml_raw()` per-call file I/O is
removed from the hot path. `OSError` in `_load_local_pricing()` now emits the
same stderr warning as decode/value errors. A sane multiplier ceiling (≤ 10)
is enforced on both the remote and local paths.

## Cache scoping

`state_integrity._MODE_CACHE` is keyed by resolved `project_dir` (string path)
instead of being a process-global single value, so a `hash`-mode project no
longer poisons `project_dir=None` reads.

## Atomicity

`write_trusted_state()` writes the sidecar to its own tmp and `os.replace()`s
it, with `os.fsync` on both tmp fds before rename. The unattributed-log
rewrite in `orchestration` reads under `locked_file`, operates by index (not
`list.remove`, which drops the wrong duplicate), and writes once under the
same lock.

## TUI

`SessionStore` caps retained sessions to the most recent 500 by `start`
(the feed only ever displays `[:50]`), in both `load()` and
`read_new_lines()` — this fixes the unbounded-growth bug and bounds the
per-refresh re-sort/re-aggregate cost. Dead `SessionStore.watch_log`
(superseded by `app._watch_events`) is removed. Untrusted session-derived
strings (branch, model, project, resume_command, pr_ref, slug) are passed
through `rich.markup.escape()` before reaching `Static.update()`.

**H7 (move heavy aggregation off the event loop into
`run_worker(thread=True)`) is deferred, not done.** It is a real
architectural change to the Textual render path (compute on a worker
thread, marshal widget updates back via `call_from_thread`) that cannot
be validated without an interactive TUI run, which this environment can't
do. Shipping an unverified threading refactor is riskier than the latency
it removes. H8 already bounds the work per refresh to ≤500 sessions, which
removes the unbounded cliff; the residual fixed-cost refresh is acceptable
until the threading change can be tested interactively. Tracked as a
follow-up.

## Input validation

- `cli_setup.adopt`: slug validated against `^[A-Za-z0-9._:/-]+$`, rejected
  with a clear `typer.Exit(1)` otherwise.
- `gemini_history.find_session_file`: `session_id` validated against the same
  hex/UUID regex `codex_app` already uses before going into a glob.
- `auto_timer`: project slug routed through `ai_log._safe_field`.

## Smaller correctness fixes

- `db.py`: each migration wrapped in an explicit transaction; duplicate-column
  `ALTER` tolerated so a half-applied migration self-heals.
- `outcomes._best_pr_for_session`: normalize session times to UTC before
  differencing the gh `created` timestamp.
- `config_history`: anchor slug regex to `^\+\s*slug\s*=`, ignore
  `client_slug`/`project_slug`, reset `current_slug` on `@@` hunk boundaries.
- `db._sync_timeclock`: pre-`SELECT` existence check so resync does not
  overcount "added" (mirrors the sessions path).
- `achievements`: `_watch_streak` uses the existing `_prev_day` helper;
  `_clean_watch_days` scopes strictly to the watch `[start, end]` interval.
- `dashboard._daily_model_chart`: drop the fabricated per-segment tooltip
  (or label "approx") so numbers reconcile with the model table.
- `ledger`: plan match respects the plan active window; final cent reconciled
  by largest remainder so allocated total == plan cost.
- `service.py`: chmod existing accepted token file to 0600.
- `pricing.py:248`: multiplier ceiling (covered above).
- Consolidate triple proof-score into `reports.py`; dedupe
  `tool_icon`/`duration_str` to `formatters.py`.
- `cli`: shared `_safe_auto_timer_close()` logging via `_log_error`;
  shared `resolve_target_dir(prefer_hub=...)`.
- `cli_session.check-log`: drop the redundant `from_log_line` side-effecting
  call.
- `codex_app`: window the rollout scan by mtime; stream files line-by-line.
- `ruff format` the two drifted files.

## Test strategy

Every fix gets a regression test where behavior is observable (Decimal
rounding, unified totals, slug rejection, cache scoping, atomic sidecar,
markup escaping). Refactors rely on the existing suite staying green. Full
`pytest` + `ruff` + `mypy` + `ruff format --check` must pass before commit.
