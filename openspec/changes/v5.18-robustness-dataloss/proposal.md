# v5.18 — Robustness & data-loss hardening

## Why

The pre-release audit (`docs/reviews/2026-06-pre-release-audit.md`) found
high-severity defects where Halyard silently loses data, crashes a long-lived
worker, or 500s a whole page on reachable input. For a tool that runs
unattended (the dashboard/hub process) and is the system of record for AI
spend, silent data loss is release-gating:

- **B4-evict** (`hub_server.py`) — when the OTel accumulator cap is exceeded,
  `_evict_excess_otel` did a bare `del`, silently dropping genuine in-flight
  sessions before they reached the ledger.
- **B6** (`otel_receiver.py`) — four robustness defects: no socket read
  timeout (slowloris exhausts the unbounded thread pool); the flush daemon
  `_flush_loop` had no try/except, so one raise in `_finalize_one`
  permanently killed the only flush thread; `flush_stale` popped sessions out
  of the accumulator *before* finalizing, losing them on a mid-loop raise;
  and `_acc` had unbounded cardinality keyed on wire-supplied session id (OOM
  via id-spray).
- **B18** (`timeclock_repair.py`) — once repair triggered, the rewrite
  silently dropped any line with the seconds-optional `HH:MM` timestamp form
  (which hledger natively accepts) and any line failing a strict parse,
  erasing valid hand-entered billable time despite a docstring promising
  manual entries are "preserved verbatim".
- **B20** (`tui/store.py`) — branch filtering scanned the dead legacy
  `branch:` *tag*, but all current collectors write the branch as the
  `branch=` *field*, so branch filtering was silently dead (always "no
  branches", zero matches) even though every row displayed its branch.
- **B21** (`tui/store.py`) — live-tail `read_new_lines()` opened the log with
  the platform default encoding while the writer uses UTF-8, so a non-ASCII
  session on a non-UTF-8 locale mis-decoded or raised, killing the live-update
  worker.
- **B22** (`dashboard.py`) — the wake-panel "previous month" link called
  `_shift_month(period, -1)` with no lower clamp, so `?month=0001-01` reached
  year 0 → `ValueError` → unhandled 500 that took down the whole render.
- **B23** (`service_providers/launchd.py`, `systemd.py`) — both service unit
  files were written under default umask (often world-readable 0o644),
  disclosing the executable path, project dir, and port to any local user.

## What changed

- **B4-evict:** `_evict_excess_otel` now returns the removed accumulators; the
  caller finalizes-and-writes each (mirroring `flush_stale`) instead of `del`.
- **B6:** set `_Handler.timeout = 10`; wrap `_flush_loop` body in try/except
  so the daemon never dies; finalize-then-pop (re-insert on failure) so a
  partial flush retries; bound `_acc` with an LRU cap that finalizes on
  eviction.
- **B18:** accept the seconds-optional `HH:MM` form, preserve any line not
  matching a known-bad pattern, and surface a count of dropped lines.
- **B20:** read `session.branch` (the field) in `branches()` and
  `filter(branch=...)`.
- **B21:** open with `encoding="utf-8", newline=""` and guard the read so a
  decode error degrades gracefully rather than killing the watch loop.
- **B22:** clamp the previous-month target to a sane lower bound so no prev
  link is emitted below it; no ValueError, no 500.
- **B23:** `os.chmod(path, 0o600)` immediately after writing each unit file.

## Out of scope

- The OTLP receiver and hub also have an *unauthenticated write endpoint*
  surface (B4-auth) — that is v5.19 (localhost auth hardening), done
  separately with the owner in the loop. This changeset touches only the
  data-loss/robustness paths, not auth/routing.
- Surfacing the B18 dropped-line count through the CLI
  (`cli_timeclock.py`) is a small follow-up (the repair function now returns
  the count; wiring it to user-facing output is a separate edit).
- The B22 template still renders the prev `<a>` unconditionally; at the
  calendar floor it emits an empty `href=""` (benign — reloads the page). A
  cosmetic `{% if wake_prev_href %}` guard in `dashboard.html.j2` is a
  follow-up.

## Success criteria

- An over-cap OTel session is finalized to the ledger, not dropped.
- The OTel flush daemon survives a `_finalize_one` exception; no session is
  lost on a partial flush; the accumulator cannot grow unbounded.
- `timeclock repair` preserves valid `HH:MM` manual entries and reports any
  drops.
- TUI branch filtering returns real results; live-tail survives non-ASCII on
  any locale.
- `?month=0001-01` does not 500 the dashboard.
- Service unit files are mode 0o600.
- Full suite green; ruff + mypy clean. Each fix has a regression test.
