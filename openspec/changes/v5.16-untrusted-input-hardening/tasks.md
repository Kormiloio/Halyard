# v5.16 — Tasks

Source: `docs/reviews/2026-06-pre-release-audit.md` (blocker IDs in brackets).
Fix order: cheapest/highest-leverage first.

## B1 — non-finite cost/credits floats [ai_log.py, usage.py] ✅

- [x] `ai_log.py`: `import math`.
- [x] Positional `cost_usd` guard (~992): reject `not math.isfinite(...)`.
- [x] `FLOAT_4` parse handler (~1016): skip non-finite `credits`.
- [x] `usage.sum_spend` (~46): defensive `math.isfinite` skip.
- [x] Regression test (`tests/test_v516_input_hardening.py`): inf/nan/1e400
      cost rejected; credits non-finite skipped; sum_spend backstop skips
      non-finite without crash/NaN. 6 tests, green; ruff+mypy clean.

## B19 — Rich markup injection in TUI [leverage_pane.py / leverage.py] ✅

- [x] Enforce allowlist in `summarize_mcp` (root fix — `named` now actually
      "allowlisted only" as documented; context-agnostic, fixes web+TUI).
- [x] `rich.markup.escape` the phrase at the TUI render site
      (`leverage_pane.py:62`) for defense-in-depth, matching other panes.
- [x] Regression test: `x[/notopened]` filtered out of `named`; escaped phrase
      round-trips through `Text.from_markup` without `MarkupError`; allowlisted
      name still renders. Green; ruff+mypy clean.

## B8 — collector parse crashes abort import [gemini_history.py, codex_app.py, copilot.py] ✅

- [x] `_safe_int` helpers (gemini, codex) + `_safe_fromtimestamp_ms` (copilot)
      honor "return None/skip on error"; widened jsonl-rollout except to
      (OSError, ValueError, TypeError, OverflowError).
- [x] Guarded codex + copilot importer loops so one bad file skips, not aborts.
- [x] Regression test (tests/test_v516_b08_collector_parse.py, 8 tests): bad
      token field → 0/skip; batch survives a crafted file before a good one.

## B7 — windsurf path traversal [windsurf.py] ✅

- [x] `_safe_state_path`: slug `^[A-Za-z0-9._-]+$` (rejects empty/./..),
      then `resolve()` + assert `parent == ws-sessions root` before any write.
- [x] Regression test (tests/test_v516_b07_windsurf_path.py): 11 malicious ids
      (incl. the exact PoC) leave a planted victim untouched; benign id works.

## B9 — git argument injection [git_context.py, cursor.py, claude_code.py] ✅

- [x] `is_valid_git_ref` (`^[0-9a-fA-F]{4,40}$` fullmatch) gates `sha_at_start`
      before subprocess at all three call sites; `--` appended. The regex is
      the authoritative guard (non-hex → None, never reaches git).
- [x] Regression test (tests/test_v516_b09_git_refs.py): `--output=/tmp/x` and
      friends rejected; real hex SHAs still produce identical deltas.

## B10 — GitHub endpoint + log injection [outcomes.py]

- [x] Validate `repo` `^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$` (reject `.`/`..`
      components) before any `gh api repos/{repo}/...` call. `_is_safe_repo`
      guards both `_fetch_pr_by_ref` and `gh_pr_inline_comment_count`.
- [x] Route amendment field writes through `_safe_field`.
- [x] Regression test: traversal `repo` rejected; amendment field with
      spaces/`=`/newline sanitized. (tests/test_v51x_b10_b11_b12_outcomes.py)

## B11 — transient gh failure poisons PR cache [outcomes.py]

- [x] `fetch_prs_for_branch` returns None on failure (non-zero/timeout/OSError/
      JSON error), [] only for a genuine no-PR result; `resolve_sessions`
      caches only non-None results (mirrors the friction no-cache-on-failure).
- [x] Regression test: failed fetch not cached; genuine empty IS cached.
      (tests/test_v51x_b10_b11_b12_outcomes.py)

## B12 — merged PR mis-bucketed as Abandoned [outcomes.py]

- [x] `_fetch_pr_by_ref` maps `.merged`/`.merged_at` → pr_state="merged"
      before the closed/open fallback (REST `.state` is "closed" for merged).
      jq extended to extract `.merged`.
- [x] Regression test: merged PR → "merged"; genuinely closed → "closed".
      (tests/test_v51x_b10_b11_b12_outcomes.py)
- [x] Updated existing tests that encoded old behavior: B11 failure-sentinel
      tests in tests/test_outcome_sync.py (now expect None, not []).

## Gate ✅ (whole-batch v5.16–v5.18, run together 2026-06-05)

- [x] `uv run pytest --ignore=tests/test_tui.py` → 1614 passed, 0 failed.
      (test_tui.py's Textual pilot tests hang in this sandbox's event loop —
      environmental, pre-existing; its 12 pure-store tests pass separately.)
- [x] `uv run ruff check .` + `ruff format --check .` clean (253 files).
- [x] `uv run mypy src/` clean (102 files).
- [x] One pre-existing time-cliff casualty surfaced by the gate
      (test_v54_dashboard_templating.py — a 10th file v5.14 had deferred) and
      fixed with the same freeze fixture. NOT caused by these blocker fixes.
- [x] Roadmap entry in `openspec/project.md` (entry 90); audit report
      fix-status table updated (`docs/reviews/2026-06-pre-release-audit.md` §0).

## Scope note

The outcomes agent grouped B11 (cache failure) and B12 (merged-PR state) into
this changeset because they share `outcomes.py` with B10. They are correctness
fixes rather than pure input-hardening; documented here for locality.
