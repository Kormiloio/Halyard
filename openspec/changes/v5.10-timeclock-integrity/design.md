# Design — v5.10 Timeclock integrity

Two independent pieces: a root-cause fix (stop producing corruption) and a
repair tool (clean up what's already there). The append-only `ai-sessions.log`
is untouched; only `time.timeclock` is in scope, and only via diff-and-confirm.

## Part 1 — Hub auto-presence survives restart (root cause)

The Hub's auto-presence lives only in `ActiveState` (memory). On every restart
the in-memory `auto_project` resets to `None`, so the next activity ping opens a
fresh `i` while the previous one is never closed → the `i i i … o` corruption.

**Fix:** persist auto-presence to `~/.halyard/auto-timer` (the same key=value
file the standalone `auto_timer` module already uses) and reconcile it on
startup. The file becomes the single source of truth shared by both the Hub and
the Hub-down standalone path.

- `auto_timer.py` gains thin public helpers over the existing private state
  functions: `write_presence(project, timeclock, started, last_activity)`,
  `read_presence() -> dict[str, str]`, `clear_presence()`. Format unchanged
  (`project=`, `timeclock=`, `started=`, `last_activity=`).
- `hub_server._persist_auto_presence_locked()` mirrors `self.state` to the file
  (or clears it when `auto_project is None`). Called inside the existing lock in
  `_record_presence_activity` and `_update_presence`; `_close_presence_now`
  clears it.
- `hub_server._reconcile_auto_presence(now=None)` runs in `_load_state()` (i.e.
  in `__init__`, before any thread serves traffic):
  - read the file; empty / malformed → clear and return.
  - `now - last_activity >= INACTIVITY_MINUTES` → **close-stale**: append the
    missing `o <last_activity>` to the timeclock and clear the file.
  - otherwise → **resume**: load `auto_project/auto_started_at/auto_timeclock/
    last_presence` into `self.state` without writing a new `i` (the original
    `i` is already in the file from the prior process).

Crash window: if the process dies *between* the `i` write and the persist, that
single `i` is orphaned and won't be reconciled (the file shows no open). It is a
one-line residue, and exactly what Part 2 cleans up. The persist happens
immediately after the `i` write, inside the same lock, to keep the window
minimal.

Graceful `stop()` deliberately leaves the window open: a quick restart resumes
it; a slow one is closed-stale on next startup. No `o` is fabricated for a still-
active session.

## Part 2 — `halyard timeclock` group

New `cli_timeclock.py` (Typer sub-app `name="timeclock"`, registered via
`app.add_typer`) plus reconstruction logic in `timeclock_repair.py`.

### Reconstruction (`reconstruct_timeclock(lines) -> list[str]`)

**Idempotency gate (deviation from initial design).** Capping a *stale* clock-out
(an `o` written long after activity stopped) requires the intermediate activity
pings — which a first pass merges away. So the function first calls
`_needs_repair(lines)`: it returns the input unchanged unless the file has a
dropped open, an orphan close, or a **backward** close (negative window). A
forward clock-out far from its open is deliberately **not** flagged, because in
a clean file a legitimate multi-hour window (built from sub-30-min pings) looks
exactly like that once merged — re-flagging it would crush it to its endpoints.
This makes `repair --apply` safe to re-run and keeps `check` honest.

Single forward pass; **the original `i` line is preserved verbatim** (keeps its
exact project token — `:` vs `/` — its `;auto` tag, and any manual comment).
Only `o` lines are synthesized, and merged auto runs collapse to one window.

State `open = (orig_i_line, kind, project, start_ts, last_ts)` where
`kind = "auto"` iff the `i` line carries a `;auto` comment.

- leading comment / blank lines → emitted verbatim as the header.
- on `i` (line L, kind, proj, T):
  - if `open`, `open.kind == "auto"`, `kind == "auto"`, `proj == open.project`,
    and `T - open.last_ts <= INACTIVITY` → **merge**: `open.last_ts = T`
    (drop this `i`; it folds into the window).
  - else → flush the current `open` (if any), then `open = (L, kind, proj, T, T)`.
- on `o` (T): if `open` → `open.last_ts = T`; flush; `open = None`. Orphan `o`
  (no open) is dropped.
- EOF: a trailing open that contains **more than one ping** (a dropped-open run,
  which is what triggered reconstruction) is flushed at `last_ts`. A **lone**
  trailing open is left as-is — it may be a live in-progress window, so its
  single `i` is never given a fabricated close.
- `flush(open)` emits `open.orig_i_line` then `o <last_ts>` (`%Y-%m-%d %H:%M:%S`).

**Clock-out handling — the `merged` flag (key correctness point).** The
auto-timer only ever writes `o` at the *last activity* (`last_presence`), never a
far-future "stale" timestamp. So a **clean single-`i`/`o` pair is authoritative**
— even a 14-hour overnight span is a correctly-recorded continuous session (the
30-min-gap guarantee held; an agent or long task kept pinging). The **corrupted**
shape is the *multi-`i` run* (dropped opens), where state was cleared between
pings. The reconstructor therefore tracks `_Open.merged` (set when a later `i`
folds into the window):
- `merged is False` (clean pair) → **trust the `o` verbatim**; only a *backward*
  close is dropped. This is what preserves legit multi-hour windows and makes the
  function idempotent on already-clean data.
- `merged is True` (dropped-open run) → the timer was pinging, so a close beyond
  `INACTIVITY` of the last ping is stale → **cap at the last real activity**.

This distinction matters: an earlier draft capped *every* `o`, which silently
under-counted by ~27h on the dev machine by crushing two legitimately-recorded
long sessions (a 14.2h overnight + a 9.3h `git/Halyard` window).

This heals the 320 sub-30-min `i→i` runs (merge), splits the 41 ≥30-min gaps
into separate windows (idle not billed), and closes every dangling open. Manual
`i`/`o` pairs pass through with only their `o` re-emitted at the same timestamp.

### Commands

- `halyard timeclock check` — read-only. Prints `timeclock_anomalies`
  (dropped opens / orphan closes) and current vs. reconstructed counted hours +
  window count. Exit 0 always.
- `halyard timeclock repair` — dry-run by default: prints a unified diff
  (`difflib.unified_diff`) and the before/after summary, then tells the user to
  re-run with `--apply`. With `--apply`: copies the file to
  `time.timeclock.bak-<UTC timestamp>`, then atomically writes the reconstructed
  content, then prints the summary. Honours "no silent writes".
- Both accept `--timeclock PATH` (default: `time.timeclock` in the project dir
  from `find_project_dir()`).

## Part 3 — test-isolation leak (second root cause)

`test_auto_timer.py` isolated the timeclock to `tmp_path` but its autouse
cleanup `unlink`ed the **module-global** `_AUTO_TIMER_FILE`, i.e. the real
`~/.halyard/auto-timer`. Every `pytest` run during real work deleted the live
clock-in, orphaning it. Fix:

- `conftest.py` gains an autouse `_isolate_auto_timer` (mirrors `_isolate_registry`)
  that points `halyard.auto_timer._AUTO_TIMER_FILE` at a `tmp_path_factory`
  path for every test — production code reads the global at call time, so all
  tests' code-under-test is covered.
- `test_auto_timer.py` stops importing the constant by value; it references
  `auto_timer._AUTO_TIMER_FILE` (the patched attribute) and drops its
  real-file `unlink` fixture.

Verified: seeding a real `~/.halyard/auto-timer`, running the suite, and
confirming the file survives.

## Tests

`tests/test_v510_timeclock_integrity.py`:
- reconcile resume (recent file → in-memory state set, no new `i`).
- reconcile close-stale (old file → `o` appended at last activity, file cleared).
- persist round-trip (activity writes the file; close clears it).
- reconstruct: auto run merges under 30 min; splits over 30 min; manual entries
  preserved verbatim; orphan `o` dropped; trailing auto closed, trailing manual
  left open; project change splits the window.
- `check` summary numbers match a known fixture.
All under `perf_ceiling` where timing matters; ruff + mypy clean; full suite
green.
