# v5.33 — Tasks

## Code

- [x] `reconcile_from_sessions(lines, sessions)` in `timeclock_repair.py`,
      returning `(new_lines, recovered_minutes, skipped_minutes)`.
- [x] Reuse `auto_timer._uncovered_spans` — one copy of the interval
      arithmetic, not two.
- [x] Fold each proposal into `covered` immediately so overlapping sessions
      cannot double-bill.
- [x] Skip sessions longer than `_MAX_SESSION_SECONDS`; report the total.
- [x] `_windows_from_lines`: ignore unclosed `i` entries.
- [x] `--from-sessions` flag on `timeclock repair`.
- [x] `_emit` shared by both modes so the dry-run/backup/atomic-write
      contract cannot drift.

## Tests (`tests/test_v533_repair_from_sessions.py`)

- [x] Recovers the observed lost stretch.
- [x] Overlapping sessions bill once; identical sessions bill once.
- [x] A fully covered session proposes nothing; partial recovers only the gap.
- [x] Idempotent — re-running after apply proposes nothing.
- [x] Never proposed outside a session; idle between sessions unbilled.
- [x] History appended, never rewritten.
- [x] An open entry does not suppress recovery.
- [x] Backwards sessions ignored.
- [x] An implausibly long session is skipped; one at exactly the cap counts;
      a skipped row does not suppress legitimate ones.
- [x] CLI: dry run writes nothing; `--apply` backs up first; a clean
      timeclock reports and exits.

## Verified against real data

- [x] Unguarded first implementation proposed **647.2 h** — traced to two
      imported Codex rollouts (653 h and 149 h) that were 89% of all session
      time.
- [x] With the bound: **71.9 h** proposed, 8.4 h → 80.3 h, ≈2.0 h/day across
      the 40-day window.
- [x] Not applied to the maintainer's ledger — that is their call.

## Gates

- [x] `uv run pytest`
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Out of scope (recorded)

- [ ] The doctor coverage check from the v5.26 spec — threshold still needs
      tuning against real data.
- [ ] README wording on what auto-detected human time counts.
