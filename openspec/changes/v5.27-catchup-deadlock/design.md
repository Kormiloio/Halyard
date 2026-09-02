# Design: v5.27 — Catch-up watermark deadlock

## The invariant being violated

> A guard that rejects a row must never also prevent the *next* row from
> being valid.

`session_is_implausible` breaks it: rejecting the row leaves the
watermark unadvanced, which guarantees the next row is rejected for the
same reason. The failure is absorbing — there is no exit.

Every fix below follows from restoring that invariant.

## 1. Clamp the catch-up reach

In `handle_stop_hook`, the watermark currently sets `start` unbounded:

```python
watermark = _last_recorded_end(project_dir, str(payload_session_id))
if watermark is not None:
    start = watermark
```

Replace with a bounded reach. `_CATCHUP_MAX_REACH` (proposed: 12h, i.e.
`_MAX_SESSION_SECONDS`) is the furthest back a single catch-up row may
anchor:

```python
if watermark is not None:
    start = max(watermark, end - _CATCHUP_MAX_REACH)
```

so the span can never exceed the plausibility limit and the row is
always writable.

**But do not stop there** — a clamped row would claim 12 hours of work
that did not happen. See (2).

## 2. Bound the row to real turns

The transcript records a timestamp per turn, and `_read_from_transcript`
already computes `start_dt` / `end_dt` for the turns it read.

Preference order for the row's `start`:

1. `ts.start_dt` when present and within the clamp window — the true
   first turn read. Honest and usually tight.
2. The session-start state file (`~/.halyard/cc-session`), the current
   turn's own start.
3. The clamped watermark, as a floor.

Observed why (1) alone is insufficient: on the reference machine
`ts.start_dt` was **also** 327h old, because it is one genuinely
long-lived session id whose turns are scattered across two weeks. The
transcript bounds are not a proxy for a single turn. Hence the clamp
remains the outer bound and (1) only tightens within it.

## 3. Importer: coverage, not blanket skip

`import_claude_sessions` today:

> A session with any hook row already in the target ledger is skipped.

Replace with overlap-based coverage:

- Collect `[start, end]` for every hook row of this session id.
- Import turns from the transcript that fall **outside** every such
  interval.
- Emit rows only for uncovered bursts, split on the same idle boundary
  the auto-timer uses (`INACTIVITY_MINUTES`) so a two-week gap becomes
  several honest bursts rather than one impossible span.

This preserves the original intent — never double-count a turn a hook
already recorded — while removing the blind spot. It is the same
union-not-sum reasoning as v5.24's `uncovered_gaps`, and the two should
share an implementation if the shapes line up.

## 4. Doctor: detect the poisoned state

`_watermark_stall_check()`: for each session id with hook rows, compare
the newest ledger row's `end` against the newest transcript turn. A
transcript materially newer than the ledger, for a session that *has*
hook rows, is this defect's signature — distinct from the existing
"capture lagging" check, which keys on file mtime and would report the
same machine as merely stale.

`warning`; fix points at `halyard import-claude`.

## 5. No silent drops

Both guards currently `return 0` without a trace. Route rejections
through `_log_error` with the session id and the reason, so
`~/.halyard/diagnostic.log` shows the cause. Diagnostic level only — a
malformed-payload machine must not spam the user's terminal.

## Alternatives considered

- **Raise `_MAX_SESSION_SECONDS`.** Rejected: it moves the cliff without
  removing it, and weakens a guard that is doing its job.
- **Drop the watermark feature.** Rejected: it exists because the Stop
  hook genuinely misses turns (v3.9); removing it reintroduces that loss.
- **Advance the watermark even when the row is dropped.** Rejected:
  that converts silent data loss into silent data loss *plus* a lie about
  what was captured.

## Testing

- **Deadlock regression:** a session with a 14-day-old watermark
  produces a row, and the watermark advances. This is the test that
  would have caught the bug.
- Clamped row never exceeds `_MAX_SESSION_SECONDS`.
- Clamped row does not claim more than the turns support (uses
  `start_dt` when it is tighter than the clamp).
- Normal short gaps behave exactly as before — no regression to v3.9
  catch-up.
- Importer: backfills turns inside a hook-row gap.
- Importer: still refuses turns already covered by a hook row (both
  directions, since this is the v5.2/v5.21/v5.22/v5.23 defect family).
- Importer: a two-week gap yields several plausible bursts, none over
  12h.
- Doctor: fires on a stalled watermark; silent on a healthy session.
- Rejected rows appear in the diagnostic log.
- `perf_ceiling` for timing; no wall-clock literals.
- Every test touching a ledger `chdir`s into `tmp_path` (v5.24 guard).
