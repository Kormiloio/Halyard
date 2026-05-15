# Design

## Correction-record format

```
s 2026-01-01T09:00:00 2026-01-01T09:30:00 claude-code claude-sonnet-4-6 10000 2000 0.085
a abc123def456 project=acme:auth source=backfill confirmed_at=2026-01-08T14:00:00
a abc123def456 project=acme:billing source=manual confirmed_at=2026-01-09T09:00:00
```

The `a` line carries the SHA-256 hash (first 12 hex chars) of the original
`s` line, plus any number of `key=value` pairs. At parse time, the most
recent `a` for a given hash overrides earlier values for the same keys.

### Fold algorithm

```python
def parse_sessions(project_dir):
    sessions_by_hash = {}
    amendments_by_hash = defaultdict(list)
    for line in iter_lines(log_path):
        if line.startswith("s "):
            session = AiSession.from_log_line(line)
            sessions_by_hash[session.session_hash] = session
        elif line.startswith("a "):
            session_hash, kvs = parse_amendment(line)
            amendments_by_hash[session_hash].append(kvs)
    for session_hash, session in sessions_by_hash.items():
        for amendment in amendments_by_hash[session_hash]:
            session.apply_amendment(amendment)
    return list(sessions_by_hash.values())
```

`apply_amendment` mutates the in-memory `AiSession`. Order is the order in
which amendments appear in the file (last-write-wins for same key).

### Amendment keys allowed in v2.17

- `project=<slug>` — change attribution
- `source=<string>` — record provenance of the amendment (`backfill`,
  `manual`, `confirmed`, `correction`)
- `confirmed_at=<ISO>` — timestamp of the amendment
- `note=<string>` — free-form explanation, surfaced in dashboard

Future amendments (v3.0) add `pr_ref`, `pr_state`, `branch`, etc.

### Hash function

```python
def session_hash(line: str) -> str:
    return hashlib.sha256(line.strip().encode()).hexdigest()[:12]
```

Truncated to 12 hex chars (48 bits) for log readability. Collision risk is
negligible at the scale of a single user's log file (millions of sessions
to first 50% collision probability).

The hash is computed on the raw `s` line *before* any amendments. So `a`
records always reference the original session line, even if amendments
later change its semantic meaning.

## Locking

```python
@contextmanager
def locked_file(path: Path, mode: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield f
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

All mutators in `ai_log.py`, `orchestration.py` (timeclock + active
timer), and `invoicing.py` (counter) wrap their critical section in
`locked_file`. `flock` is advisory but cooperative — we own all the
writers, so it's sufficient.

Read paths do not lock. `parse_sessions` is allowed to see any consistent
prefix of the file. Worst case it misses a session that landed mid-read,
which the next refresh picks up.

## Shared timer functions

New module API (or extension of `orchestration.py`):

```python
def start_timer(project_dir: Path, slug: str) -> ActiveTimer
def stop_timer(project_dir: Path) -> StopResult
```

Both wrap their state changes in `locked_file` on the relevant paths.
`stop_timer` invokes `backfill_window` after the clock-out write. Both
are idempotent: starting an already-running timer raises a typed error
the caller can handle; stopping an already-stopped timer returns
`StopResult(was_running=False)`.

The CLI `start` and `stop` commands and the dashboard `do_POST` handler
both call these functions. The dashboard removes its 30 lines of
duplicated logic.

## Error visibility

Replace:

```python
except Exception:
    pass
```

with:

```python
except Exception as e:
    _log_error("backfill_window failed", e)
    console.print(f"[yellow]Warning:[/] attribution backfill skipped ({type(e).__name__}). See ~/.halyard/halyard.log.")
```

`_log_error` writes a timestamped traceback to `~/.halyard/halyard.log`.
The user sees a one-line warning; the log captures detail. Critical
paths (init, config-driven invoice generation) escalate to non-zero exit
codes; opportunistic paths (backfill, sync, git context detection) warn
but continue.

## Migration

Existing log files have only `s` lines and the legacy `project=…` field
already attached at write time. Those continue to parse correctly — no
amendments to fold, attribution is whatever the original `s` line says.

Existing users who have run `assign_unattributed_sessions` or
`confirm_session_attributions` in the past have logs that were already
rewritten in place. That state is fine: the rewrites set the `project=`
field on the original `s` line, which v2.17 reads natively. Any future
attribution change will append `a` records instead of mutating.

A hidden `halyard log normalize` command (deferred to v2.18 utilities)
can convert a mixed-format log to canonical "all `s` lines pristine, all
attribution in `a` records" if anyone wants the cleanest archive.

## Performance

Append + flock on a typical local filesystem is ~10µs. `parse_sessions`
gains O(amendments) work — for a typical user with attribution corrections
on <5% of sessions, this is negligible. The SQLite cache (v2.14) absorbs
the cost for users with very large logs.

The fold step happens in memory after the linear scan, so it is O(n)
total. No regression vs the pre-v2.17 parser.

## Deferred work

- **M4 — multiple concurrent timers.** The locking changes here make M4
  cleaner to ship (locks already exist) but don't deliver it. v2.19.
- **Cryptographic tamper-evidence.** Strategy lists this; implementation
  is deferred until at least one enterprise design partner asks for it.
