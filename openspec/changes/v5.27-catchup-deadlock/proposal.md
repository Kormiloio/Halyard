# Proposal: v5.27 — Catch-up watermark deadlock permanently kills capture

## Why this exists

A Claude Code session that goes **12 hours without a captured turn stops
being captured — permanently.** Not until restart, not until the next
prompt: forever, for that session id. It fails silently with exit 0.

On the reference machine this ate **two weeks** of capture (2026-08-11 →
2026-08-25) across 24 work bursts totalling 8.6 hours, while the hooks
appeared healthy, the binary worked, and `doctor` reported hooks
installed.

This is the most severe defect found so far: total, silent, permanent
data loss in the capture path, triggered by something as ordinary as
closing a laptop overnight.

## The deadlock

`handle_stop_hook` has a catch-up feature (v3.9): if turns were missed,
anchor the row's start to the last recorded end for this session so the
gap is backfilled rather than dropped.

```python
watermark = _last_recorded_end(project_dir, str(payload_session_id))
if watermark is not None:
    start = watermark
```

`session_is_implausible` rejects any span over `_MAX_SESSION_SECONDS`
(12h) as physically impossible for one turn — a sound guard against
synthetic payloads.

Together they deadlock:

1. Capture stops for >12h (closed laptop, misrouted Hub, any reason).
2. Next Stop hook builds `start = watermark`, `end = now` → a >12h span.
3. `session_is_implausible` → **True** → row dropped, exit 0, no warning.
4. No row written, so **the watermark never advances**.
5. Every subsequent Stop rebuilds the same impossible span and is dropped.

Reproduced exactly:

```
span            = 347.0h
has_evidence    = True
is_implausible  = True   <-- dropped here
```

The guard that exists to protect data integrity is what destroys the
data. And because the drop is silent, every downstream signal looks fine.

## Why the importer doesn't save you

`import_claude_sessions` deliberately **skips any session that already
has hook rows** in the target ledger (v5.21), on the stated assumption
that "the hook's own watermark catch-up heals intra-session gaps".

The hook cannot heal — that is this bug. So the two mechanisms cover each
other's blind spot and neither runs. Recovery is impossible without
manual intervention, even though the transcript on disk has every turn.

## What changes

- **The Stop hook can never deadlock.** When the watermark gap exceeds
  the plausible limit, clamp the reach so a row is always writable and
  the watermark always advances. A capture guard must not be able to
  permanently disable capture.
- **Bound the row honestly.** A clamped catch-up must not claim a 12-hour
  session. Prefer the transcript's own turn timestamps for the recent
  burst; the transcript knows when the work happened.
- **The importer backfills gaps.** Replace "skip any session with hook
  rows" with "import turns not already covered by a hook row's
  [start, end]". Same double-count protection, without the blind spot.
- **`doctor` surfaces a poisoned watermark.** A session whose newest
  transcript turn is far newer than its newest ledger row is exactly this
  defect; say so rather than reporting healthy hooks.
- **A dropped turn is never silent.** Any guard that discards a candidate
  row logs it via `_log_error`, so the next `doctor` has something to
  find.

## Success criteria

- A session idle for >12h resumes capturing on its next turn, with a
  plausible row, and the watermark advances.
- No row ever claims a span longer than the work it represents.
- `import-claude` backfills turns inside a hook-row gap and still refuses
  to double-count turns already covered.
- The reference machine's 24 missed bursts are recoverable from the
  existing transcript.
- `doctor` reports the poisoned state rather than "hooks installed".

## Out of scope

- Raising or removing `_MAX_SESSION_SECONDS`. The 12h guard is correct;
  the bug is that failing it drops the row *and* the watermark.
- Reworking catch-up into per-turn rows. Larger change; the clamp plus a
  working importer covers the loss.

## Risks and trade-offs

- **Clamping loses attribution of the old gap.** The clamped row covers
  recent work only; older missed turns come back via the importer rather
  than the hook. That is the correct division — the importer can see the
  whole transcript, the hook cannot.
- **Importer change touches double-count protection**, the defect family
  this repo has already paid for four times (v5.2, v5.21, v5.22, v5.23).
  Overlap-based coverage must be tested hard, both directions.
- **Silent-drop logging could get noisy** on machines with genuinely
  malformed payloads. Log at diagnostic level, not user-facing output.
