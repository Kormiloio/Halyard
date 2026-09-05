# v5.27 — Tasks

## Core — break the deadlock

- [ ] `_CATCHUP_MAX_REACH` in `claude_code.py`, derived from
      `_MAX_SESSION_SECONDS` (single source of truth).
- [ ] Clamp the watermark anchor: `start = max(watermark, end - reach)`
      so a catch-up row is always writable.
- [ ] Tighten within the clamp using `ts.start_dt` when it is later than
      the clamped floor, so the row does not claim unworked hours.
- [ ] Verify the same watermark path is not duplicated in `cursor.py` or
      `hub_server.py`; if it is, fix there too.

## Importer — coverage instead of blanket skip

- [ ] Replace "skip any session with hook rows" with overlap-based
      coverage: import only turns outside every hook row's `[start, end]`.
- [ ] Split uncovered turns into bursts on the `INACTIVITY_MINUTES`
      boundary so a long gap yields plausible rows, never one >12h span.
- [ ] Reuse `uncovered_gaps`-style union logic if the shapes line up.

## Observability

- [ ] Route both guard rejections through `_log_error` with session id and
      reason (diagnostic level only, never user-facing spam).
- [ ] `_watermark_stall_check()` in `doctor.py`: newest transcript turn
      materially newer than newest ledger row **for a session that has
      hook rows**. Distinct from the mtime-based capture-lagging check.

## Tests (`tests/test_v527_catchup_deadlock.py`)

- [ ] **Deadlock regression:** 14-day-old watermark → a row is written and
      the watermark advances. The test that would have caught this.
- [ ] Clamped row never exceeds `_MAX_SESSION_SECONDS`.
- [ ] Clamped row uses `start_dt` when tighter — no over-claim.
- [ ] Short gaps unchanged (no v3.9 catch-up regression).
- [ ] Importer backfills turns inside a hook-row gap.
- [ ] Importer still refuses turns already covered (both directions).
- [ ] A two-week gap yields several bursts, none over 12h.
- [ ] Doctor fires on a stalled watermark; silent on a healthy session.
- [ ] Rejected rows are logged.
- [ ] Timing assertions use `perf_ceiling`.
- [ ] Ledger-touching tests `chdir` into `tmp_path` (v5.24 guard).

## Recovery (reference machine)

- [ ] Recover the 24 missed bursts (8.6h, 2026-08-11 → 2026-08-25) from
      the existing transcript via the fixed importer.
- [ ] Reinstall the user's `halyard` from the fixed build — hooks run the
      pipx binary, so a repo-only fix never reaches them.

## Docs

- [ ] README troubleshooting: "capture stopped and never resumed".
- [ ] Update roadmap status and test count in `openspec/project.md`.

## Gate

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy src/`
- [ ] `uv run pytest`
