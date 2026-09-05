# v5.26 — Tasks

Scope shipped: the **core fix** only. Retroactive recovery, the doctor
check, and README wording are deferred to a follow-up and listed at the
bottom — recorded, not dropped. See the "Implementation notes" section of
`design.md`.

## Core fix — session-span coverage

- [x] `auto_timer_cover_session(project, timeclock, start, end)` in
      `auto_timer.py`: append-only, idempotent, never extends past `end`,
      never overlaps existing coverage.
- [x] `_uncovered_spans()` split out so the interval arithmetic — the part
      that can silently double-bill — is testable on its own.
- [x] `safe_cover_session()` wrapper: hook-safe, logs instead of raising,
      mirroring `safe_auto_timer_close`.
- [x] Call it from every stop hook after the session row is built:
      `claude_code`, `cursor`, `gemini_cli`, `windsurf`.
- [x] Leave `INACTIVITY_MINUTES` at 30 and keep it the single source of
      truth. Raising it would bill genuine idle.
- [x] ~~Mirror both behaviours in `hub_server.py`.~~ **Not needed as
      built** — coverage is asserted against the timeclock file, never
      through the presence state machine, so the Hub's independent idle
      close cannot defeat it. Pinned by
      `test_coverage_is_independent_of_presence_state`, which fails if a
      future refactor routes coverage through presence. Design amended.

## Tests (`tests/test_v526_auto_timer_undercount.py`)

- [x] One prompt + a 2-hour turn → ~2h20m counted, not ~19m (the observed
      2026-08-11 case).
- [x] Mid-turn stale close (presence state cleared, hub calls made fatal) →
      the stop hook still recovers full coverage.
- [x] Idempotence: replaying a stop writes no duplicate coverage.
- [x] A fully covered span writes nothing at all.
- [x] Only the *gap* is added, not the whole span (union, not sum).
- [x] No over-claim: coverage never extends past the session `end`.
- [x] Genuine idle *between* sessions is still excluded.
- [x] History is never rewritten — existing lines byte-identical after.
- [x] A manual timer wins, same precedence as `auto_timer_activity`.
- [x] Backwards / zero-length spans write nothing.
- [x] `_uncovered_spans` parametrised over 10 interval arrangements
      (disjoint, touching, straddling, enclosing, unsorted input).

## Gate

- [x] `uv run pytest` — 1864 passing.
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `design.md` amended with the `hub_server` deviation and shipped scope.
- [x] `openspec/project.md` — roadmap entry + test count.

## Deferred to a follow-up (recorded, not done)

- [ ] `halyard timeclock repair --from-sessions`: reconcile the timeclock
      against `ai-sessions.log` to recover days already lost — including
      the observed 2026-08-11 day. Union semantics, dry-run by default,
      timestamped backup on `--apply`, unified diff, report recovered
      hours. A new user-facing CLI mode with its own safety contract.
- [ ] `_human_time_coverage_check()` in doctor: warn when counted human
      time is materially below AI session time for the same period. The
      design flags the threshold as needing tuning against real data first
      — a check that cries wolf is worse than no check.
- [ ] README: what auto-detected human time counts, and what it does not.
