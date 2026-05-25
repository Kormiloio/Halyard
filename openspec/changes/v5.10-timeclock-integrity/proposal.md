# v5.10 — Timeclock integrity (presence persistence + repair)

## Why

The auto human timer has been silently under-billing. On this machine the
`time.timeclock` holds **400 clock-ins but only 39 clock-outs — 361 dropped
opens** (`timeclock_anomalies` confirms `(361, 0)`). Of the 361 consecutive
`i→i` cases, **320 have <30-minute gaps**: under the auto-timer's own
presence-window model those should have been a *single* continuous session, not
a fresh clock-in. The work time between them is dropped.

The file is corrupt enough that `parse_timeclock` emits out-of-order pairs (even
negative durations). A faithful reconstruction (trust clean clock-outs, cap only
dropped-open runs) yields **~60.9h across 82 windows**; the raw file yields
garbage. The dashboard only *warns* ("unclosed clock-in(s) overwritten — time
may be undercounted") — there was no way to fix it.

**Root cause.** The Hub keeps auto-presence purely in memory
(`hub_server.py` `_record_presence_activity` / `_close_*_presence`). On startup
it recovers the *manual* timer but never the auto-presence state. Every Hub
restart (or crash) therefore orphans an open `i`: the in-memory `auto_project`
resets to `None`, so the next activity ping writes a brand-new bare `i` while the
prior one is never closed. A long-running daemon that restarts on upgrades,
reboots, or crashes accumulates exactly this `i i i … o` pattern.

## What changes

1. **[HIGH] Hub auto-presence survives restart (root cause).** The Hub persists
   its auto-presence to `~/.halyard/auto-timer` (the same key=value file the
   standalone `auto_timer` module already uses) on open / activity-refresh /
   close. On startup the Hub reconciles that file: if the last activity is
   within `INACTIVITY_MINUTES`, it *resumes* the open window in memory (no new
   `i`); if it is older, it *closes* it (writes the missing `o` at last activity)
   before serving traffic. Restarts and crashes stop orphaning clock-ins, and
   the file becomes the single source of truth shared by both code paths.

2. **Timeclock repair command.** A new `halyard timeclock repair` reconstructs
   clean `i`/`o` windows from corrupted auto entries by merging activity
   timestamps under the `INACTIVITY_MINUTES` (30-min) rule — the same rule the
   live timer applies. **Manual entries (no `;auto` tag) are preserved
   verbatim**; only `;auto` runs are rebuilt. Dry-run by default (prints a
   unified diff and the before/after counted hours); `--apply` writes after a
   timestamped backup. Honours the "no silent writes" non-negotiable.

3. **`halyard timeclock check`.** A read-only companion that reports
   `timeclock_anomalies` (dropped opens / orphan closes) and the reconstructed
   vs. current counted hours, so the corruption is visible from the CLI, not
   just the dashboard.

4. **[HIGH] Test-isolation leak (second root cause).** `test_auto_timer.py`'s
   autouse fixture called `_AUTO_TIMER_FILE.unlink()` on the **real**
   `~/.halyard/auto-timer` (it isolated the timeclock to `tmp_path` but not the
   state file). Running `pytest` during real work therefore deleted the live
   clock-in, orphaning it — and since the project is developed test-first, this
   silently dropped opens on nearly every run. Added a conftest autouse
   `_isolate_auto_timer` fixture (mirroring `_isolate_registry`) that redirects
   `_AUTO_TIMER_FILE` to a throwaway path for **every** test, and reworked
   `test_auto_timer.py` to read the patched module attribute. Proven: a test run
   no longer deletes a seeded real state file.

## Impact

- Affected: `hub_server.py` (presence persistence + startup reconcile),
  `auto_timer.py` (shared serialize/parse helpers for the state file), new
  `cli_timeclock.py` + a `timeclock` Typer group registered in `cli.py`, new
  `timeclock_repair.py` reconstruction logic in/near `reports.py`.
- No format change: the file stays hledger timeclock; manual entries untouched;
  repair is opt-in and diffed. The append-only `ai-sessions.log` is not touched.
- Tests added for: restart reconcile (resume + close-stale), repair
  reconstruction (auto-only, manual preserved, project-change split), and the
  `check` summary.
