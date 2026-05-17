# v2.71 — Pre-OSS review hardening: Tasks

Status: **COMPLETE 2026-05-16 (1255 tests passing).** All verified
defects from the pre-OSS multi-pass review fixed; gate green.

## Ship-blockers
- [x] Hook crash backstop: `cli_hooks._run_hook` wraps every hidden
  hook entry point (catches `BaseException`, re-raises
  `KeyboardInterrupt`/`SystemExit`, logs to stderr, exits 0);
  tolerant `_coerce_int` in `claude_code`/`gemini_cli`; `OSError`
  added to `_read_state` readers (claude_code/cursor)
- [x] v2.38 escaping: `usage_pane` remote + favorite_model,
  `branch_modal._branch_label` branch; `test_v238` extended
- [x] `tags` percent-encoded per element (`_encode_free_text` /
  `_decode_tag`); legacy comma form still parses (no underscore→space
  for tags); v2.24 branch promotion still works post-decode

## High-value
- [x] `append_session` no longer parses the log; milestone easter
  eggs moved to `maybe_emit_milestones`, called once by the three
  interactive stop collectors (bulk import now O(n))
- [x] `db.get_db()` sets `busy_timeout=5000` + `journal_mode=WAL`
  (best-effort, suppressed on read-only FS)
- [x] `cli_report._fail()` — `--json` failures emit `{"error":…}`;
  human errors → `err_console` (stderr). Routed: report `--month`,
  usage `--range`/no-project, evidence `--verify`+`--json`/`--month`
- [x] `store.read_new_lines()` applies `a ` records incrementally
  (`_apply_amendment_line`); full reload only if the target session
  isn't in memory; `_parse_session_line` tags `_raw_hash`

## Lower
- [x] `codex_app._iter_jsonl_lines` 25 MB cap + symlink reject
- [x] `gemini_history._read_capped` symlink reject; `find_session
  _file` uses `_safe_mtime` (OSError-guarded)
- [x] `_do_install_hook_claude` `_settings_unchanged` byte-stable
  no-op guard
- [x] `gemini_otel._iter_json_objects` recovery-scan max-attempts cap
- [x] `app.py` `_health_checks` / morse-stop excepts `self.log.error`
- [x] `ledger` accumulates `direct_usd`/`allocated_usd` as `Decimal`
- [x] `db.last_sync()` returns `None` instead of raising `DbError`
- [x] `pricing` warnings via Rich stderr console (not `print`)
- [x] `pyproject` runtime deps upper-bounded
- [x] `project.md` test count + v2.71 roadmap entry
- [x] Documented (not built): amendment trust gap; unknown-kv
  preservation — recorded in design Non-goals

## Follow-up risk list (folded in)
- [x] Risk 1 (typst/$PATH, Low): `render_pdf` invokes the resolved
  `shutil.which("typst")` path, not the bare name (no second $PATH
  resolution at exec). Accepted as residual otherwise — same trust
  model as git/open/xdg-open; PATH compromise is already full RCE
- [x] Risk 2 (timeclock overlaps, Low): `timeclock_anomalies()`
  detects dropped opens (double-`i`) and orphan closes (`o` with no
  `i`); `_timeclock_check` raises a `warning` so doctor/dashboard
  surface it. Silent under-billing → visible, actionable nudge. We
  do NOT reconstruct concurrent entries (hledger is strictly
  sequential; ambiguous) — detection only

## Tests
- [x] `tests/test_v271_review_hardening.py` (18 cases) + `test_v238`
  extension (2 cases)

## Gate
- [x] `pytest` green (1260 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
