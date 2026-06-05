# v5.18 — Design

## B4-evict & B6 cap — finalize on eviction, never drop

Both the hub (`hub_server.py`) and the receiver (`otel_receiver.py`) bound
their in-memory OTel accumulator. The defect was identical in spirit: when the
bound is hit, the oldest accumulator was `del`'d, discarding an in-flight
session's accumulated tokens/turns before they reached the ledger. The fix
makes eviction go through the same finalize-and-write path a normal flush
uses, so a capacity bound degrades to "write early", never "lose silently".
The LRU key reuses the existing `last_update` field — no new wire fields.

## B6 daemon survival & data-loss

Three independent hardening moves on the receiver:
1. `_Handler.timeout = 10` (matching the sibling hub handler) so a slow/half-
   open client cannot pin an unbounded `ThreadingHTTPServer` thread.
2. Wrap the `_flush_loop` body in try/except (log + continue) so a raise in
   `_finalize_one` (deleted cwd, git shellout, disk IO) cannot permanently
   kill the only flush thread — the failure mode where telemetry silently
   stops being written for the rest of the process lifetime.
3. Finalize-then-pop (or re-insert on failure) so a mid-loop exception retries
   the unflushed sessions on the next tick instead of dropping N..end.

## B18 — preserve unless known-bad

The repair rewrite was a denylist masquerading as an allowlist: it kept only
lines matching a strict `%Y-%m-%d %H:%M:%S` shape and dropped everything else,
including the perfectly valid seconds-optional `HH:MM` form hledger accepts.
The fix inverts the posture: accept the `HH:MM` form, and echo any
unparseable-but-plausible line verbatim into the output instead of dropping
it. The function now also returns a count of genuinely dropped lines so the
caller can warn the user rather than silently shrinking their billable record.

## B20 — read the field, not the dead tag

`ai_log` promotes a legacy `branch:` tag into the `branch=` field on read, but
never the reverse, and all live collectors write the field. The store's
branch index/filter still read `s.tags`, so they saw nothing. One-line-class
fix: read `s.branch`.

## B21 — match the writer's encoding

The writer and initial load use `encoding="utf-8"`; the live-tail incremental
read did not, inheriting the platform default. Open with
`encoding="utf-8", newline=""` and guard the decode so a bad byte degrades to
a skipped line rather than killing the `awatch` worker.

## B22 — clamp the month walk

`_shift_month` is sound; the caller emitted a prev link with no lower bound,
letting the user walk to year 0 and crash `datetime`. Clamp the prev target to
a sane floor (no prev link below it). Scoped strictly to the month-shift
clamp — auth/cookie/GET logic untouched (that is v5.19).

## B23 — 0o600 the unit files

`write_text` honors umask (commonly 0o644). `os.chmod(path, 0o600)` right after
the write closes the disclosure window. The containing dirs
(`~/Library/LaunchAgents`, `~/.config/systemd/user`) are deliberately left
alone — they are shared system locations that may hold the owner's other unit
files, so tightening only Halyard's file avoids clobbering unrelated perms.

## Testing

Each fix has a dedicated regression test file (`test_v518_b*`): over-cap
finalize-to-ledger (B4), daemon-survives-raise + no-loss-on-partial-flush +
timeout set (B6), `HH:MM` preserved + drop-count surfaced (B18), field-based
branch filter (B20), non-ASCII live-tail (B21), `?month=0001-01` no-500 (B22),
0o600 unit files (B23).
