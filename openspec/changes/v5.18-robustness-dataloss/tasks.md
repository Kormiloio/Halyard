# v5.18 — Tasks

Source: `docs/reviews/2026-06-pre-release-audit.md`. All implemented in the
parallel blocker-fix workflow (2026-06-05) and verified by the whole-batch
gate (see v5.16 tasks.md Gate section: 1614 passed, ruff+mypy clean).

## B4-evict — OTel eviction drops in-flight sessions [hub_server.py] ✅

- [x] `_evict_excess_otel` returns removed accumulators; caller
      finalize-and-writes them (mirrors `flush_stale`). Auth/routing untouched.
- [x] Regression test (tests/test_v518_b04_hub_evict.py): over-cap evicted
      session IS finalized to the raw ledger.

## B6 — OTel receiver robustness (4 sub-defects) [otel_receiver.py] ✅

- [x] `_Handler.timeout = 10` (slowloris).
- [x] `_flush_loop` body wrapped in try/except (daemon never dies).
- [x] Finalize-then-pop / re-insert on failure (no partial-flush loss).
- [x] `_acc` LRU cap that finalizes on eviction (no unbounded OOM).
- [x] Regression test (tests/test_v518_b06_otel_receiver.py).

## B18 — repair silently deletes valid billable lines [timeclock_repair.py] ✅

- [x] Accept seconds-optional `HH:MM`; preserve non-known-bad lines verbatim;
      return a count of dropped lines.
- [x] Regression test (tests/test_v518_b18_timeclock_repair.py).
- Follow-up (out of scope): wire the dropped-line count to user-facing output
  in `cli_timeclock.py`.

## B20 — branch filter reads dead legacy tag [tui/store.py] ✅

- [x] Read `session.branch` (field) in `branches()` and `filter(branch=...)`.
- [x] Regression test (tests/test_v51x_b20_b21_tui_store.py); migrated 6
      existing tag-based store tests/fixtures in tests/test_tui.py to the field.

## B21 — live-tail uses platform encoding [tui/store.py] ✅

- [x] `read_new_lines()` opens `encoding="utf-8", newline=""`; decode error
      degrades gracefully instead of killing the watch loop.
- [x] Regression test (tests/test_v51x_b20_b21_tui_store.py).

## B22 — wake prev-month nav 500s the page [dashboard.py] ✅

- [x] Clamp the previous-month target to a sane floor; no prev link below it.
      Scoped to the month-shift clamp; auth/cookie/GET untouched (→ v5.19).
- [x] Regression test (tests/test_v518_b22_wake_nav_clamp.py): extreme/min
      month renders without exception.
- Follow-up (out of scope): cosmetic `{% if wake_prev_href %}` guard in
  `dashboard.html.j2:92` (empty `href=""` at the floor is benign).

## B23 — world-readable service unit files [launchd.py, systemd.py] ✅

- [x] `os.chmod(path, 0o600)` after writing each unit file. Shared parent dirs
      left untouched (may hold the owner's other units).
- [x] Regression test (tests/test_v518_b23_service_file_mode.py).

## Gate ✅

Run as part of the whole v5.16–v5.18 batch — see
`openspec/changes/v5.16-untrusted-input-hardening/tasks.md` Gate section.
- [x] Roadmap entry in `openspec/project.md` (entry 90).
