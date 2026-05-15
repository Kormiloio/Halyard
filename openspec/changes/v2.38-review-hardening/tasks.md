# v2.38 — Review Hardening: Tasks

Severity from the review pass. Tick immediately on completion.

## Phase 0 — Static

- [x] `ruff format` `cli_setup.py` and `pricing.py`

## Phase 1 — Money & pricing (contract change, spec'd)

- [x] H1 — `pricing.calculate_cost` uses `Decimal`, quantize 4dp ROUND_HALF_UP
- [x] H1 — `invoicing`/`voyages` amounts quantize 2dp ROUND_HALF_UP
- [x] H2 — fold multipliers into `_merged_table`; invalidate together
- [x] H3 — `_load_local_pricing` warns on `OSError`
- [x] pricing.py:248 — multiplier ceiling (≤10) on both paths
- [x] M2 — `usage.sum_spend()` shared helper; budget/invoicing/ledger use it
- [x] Tests: Decimal determinism, unified totals, OSError warning, ceiling

## Phase 2 — Security / injection

- [x] C1 — `rich.markup.escape` session-derived strings in TUI panes
- [x] H5 — `adopt` validates slug `^[A-Za-z0-9._:/-]+$`
- [x] M8 — `gemini_history.find_session_file` validates `session_id`;
  `gemini_cli` catches `TypeError`
- [x] M9 — `auto_timer` routes project slug through `_safe_field`
- [x] Tests: markup escape, slug rejection, glob-id validation

## Phase 3 — Data integrity / robustness

- [x] H4 — `check-log` drops redundant `from_log_line` side effect
- [x] H6 — `db` migrations in explicit transaction; tolerate dup column
- [x] M1 — `_MODE_CACHE` keyed by `project_dir`
- [x] M3 — `outcomes._best_pr_for_session` normalizes to UTC
- [x] M4 — `write_trusted_state` atomic sidecar (tmp + fsync + replace)
- [x] M5 — `config_history` anchored slug regex + hunk reset
- [x] M10 — `db._sync_timeclock` existence check; `_clean_watch_days`
  window; `_daily_model_chart` tooltip
- [x] orchestration — unattributed rewrite under lock, index-based
- [x] service.py — chmod existing accepted token to 0600
- [x] Tests: cache scoping, atomic sidecar, migration self-heal, UTC PR match

## Phase 4 — TUI perf

- [ ] H7 — heavy aggregation to `run_worker(thread=True)` — **DEFERRED**
  (invasive Textual render-path change, unverifiable without an
  interactive TUI run; H8 bounds the cost. See design.md.)
- [x] H8 — `SessionStore` caps retained sessions (500)
- [x] H9 — `codex_app` streaming read + dedup-state pruning
- [x] remove dead `SessionStore.watch_log`

## Phase 5 — Dedup / low

- [x] M7 — shared `safe_auto_timer_close()` logging via `_log_error`
  (replaces two silent `except Exception: pass` blocks)
- [x] `_watch_streak` uses `_prev_day` (deletes the duplicate hand-rolled
  month math + now-unused `_days_in_month`)
- [x] `cli_db reset` confirmation (TTY-guarded `--yes`; non-TTY/automation
  unaffected)
- [ ] M6 — shared `resolve_target_dir(prefer_hub=...)` — **DEFERRED.**
  The per-command divergence (e.g. `report`/`confirm-attribution` have no
  hub fallback while `usage`/`dashboard` do) may be intentional per
  command. Unifying changes user-visible target resolution for ~12
  commands and needs a dedicated change with a per-command decision +
  tests, not a blind sweep.
- [ ] consolidate proof score into `reports.py` — **WON'T FIX (by
  design).** The dashboard vs achievements vs watch_pane variants have
  intentionally different zero-session behavior (documented decision).
  Merging them would regress intended UX. Left as-is deliberately.
- [ ] dedupe `tool_icon`/`duration_str` to `formatters.py` — **DEFERRED.**
  The dashboard `_tool_icon`/`_duration_str` return emoji+CSS; the
  `formatters` ones return ASCII. They are not interchangeable;
  "deduping" would change rendered output with zero correctness benefit
  (cosmetic churn).
- [ ] `ledger` plan active-window match + largest-remainder cent
  reconcile — **DEFERRED.** Changes user-visible monetary allocation
  distribution; LOW severity and ROUND_HALF_UP is already applied
  (Phase 1). Warrants its own change with updated golden tests rather
  than riding in a hardening pass.

## Phase 6 — Gate

- [x] `pytest` green (987 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean (69 files)
- [x] roadmap entry + status in `openspec/project.md` (item 17)
- [x] PRD/ARD reviewed — no change needed. This is a hardening pass: no
  new scope/priority. The one observable contract shift (deterministic
  cost rounding + unified spend window) is captured authoritatively in
  `specs/cost-and-spend.md`; `PRD-ai-work-ledger.md` is an explicitly
  non-spec vision doc and documents none of this mechanically.
