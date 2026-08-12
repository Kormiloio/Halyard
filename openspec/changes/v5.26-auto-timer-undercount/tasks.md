# v5.26 — Tasks

## Core fix — session-span coverage

- [ ] `auto_timer_cover_session(project, timeclock, start, end)` in
      `auto_timer.py`: append-only, idempotent, never extends past `end`,
      never overlaps existing coverage.
- [ ] Call it from every stop hook after the session row is built:
      `claude_code`, `cursor`, `gemini_cli`, `windsurf`.
- [ ] Wire `auto_timer_update_activity()` into `cursor`, `gemini_cli`,
      and `windsurf` stop hooks — today only `claude_code` calls it
      (claude_code.py:612). Secondary: it no-ops once the window has
      already been closed, which is the case that matters.
- [ ] Mirror both behaviours in `hub_server.py`. The Hub applies the idle
      policy independently and wins on any machine running The Bridge —
      fixing only `auto_timer.py` would leave the bug in place there.
- [ ] Leave `INACTIVITY_MINUTES` at 30 and keep it the single source of
      truth. Raising it would bill genuine idle.

## Retroactive recovery

- [ ] `halyard timeclock repair --from-sessions`: reconcile the timeclock
      against `ai-sessions.log`.
- [ ] Union semantics — never propose a span overlapping existing
      coverage; never invent time beyond a session's own bounds.
- [ ] Dry-run by default, timestamped backup on `--apply`, unified diff
      (match the existing `repair` contract).
- [ ] Report recovered hours in the summary.

## Doctor

- [ ] `_human_time_coverage_check()`: warn when counted human time is
      materially below AI session time for the same period.
- [ ] Tune the threshold against real data before shipping — a check that
      cries wolf is worse than no check.
- [ ] `warning` only; fix text points at `repair --from-sessions`.

## Tests (`tests/test_v526_auto_timer_undercount.py`)

- [ ] One prompt + a 2-hour turn → ~2h counted, not 30m (the observed
      case: 16:12 → 18:32 counted as 34m).
- [ ] Mid-turn stale close (simulating Hub presence polling) → the stop
      hook still recovers full coverage.
- [ ] Idempotence: replaying a stop writes no duplicate coverage.
- [ ] No over-claim: coverage never extends past the session `end`.
- [ ] Genuine idle *between* sessions is still excluded.
- [ ] Hub path and standalone path produce identical timeclocks for the
      same event sequence.
- [ ] `repair --from-sessions` recovers a known-lost day.
- [ ] `repair --from-sessions` is idempotent and does not double-count.
- [ ] Dry-run writes nothing.
- [ ] Doctor: fires on an under-counted day; silent on a healthy day;
      silent on a short day.
- [ ] Any timing assertion uses `perf_ceiling`.
- [ ] Every test touching a ledger or timeclock `chdir`s into `tmp_path`
      (v5.24 conftest guard).

## Docs

- [ ] README: explain what auto-detected human time counts, and what it
      does not.
- [ ] Update roadmap status and test count in `openspec/project.md`.

## Gate

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy src/`
- [ ] `uv run pytest`
