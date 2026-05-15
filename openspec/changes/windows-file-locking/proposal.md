# Windows-Compatible File Locking for `ai-sessions.log`

## Summary

Replace the Unix-only `fcntl.flock` path in `locked_file()` with a
cross-platform locking strategy so concurrent appends from multiple
collectors on Windows cannot interleave or corrupt the log.

## Motivation

`ai_log.py` currently does:

```python
if _fcntl is not None:
    _fcntl.flock(f.fileno(), _fcntl.LOCK_EX)
```

On Windows, `_fcntl` is `None`. The in-process `threading.RLock` keeps writes
within one Python process safe, but a second Halyard process — typical when
multiple AI collectors (Claude Code, Cursor, Gemini, Codex) all shell out to
`halyard cc-hook` / `gc-hook` simultaneously — has no OS-level coordination.
On Windows this can produce:

- Interleaved bytes inside one log line.
- Two writers reading the same "ends with newline?" snapshot and racing on
  the leading-newline rule in `_append_lines()`.
- Silent corruption that surfaces as quarantined lines.

Halyard already targets Windows (the README mentions cross-platform, and
collectors are POSIX-agnostic). This is a real gap once a Windows user has
more than one AI tool active.

## Approach options

1. **`msvcrt.locking()`** — Windows native, byte-range advisory locks.
   Wrap `_fcntl` with a thin compatibility shim that picks the right backend
   at import time.
2. **`portalocker` dependency** — small pure-Python library that does
   exactly this cross-platform wrapping. Adds one dependency.
3. **Lockfile-based** — write a sentinel `.lock` next to the log file with
   exclusive-create semantics. Most portable, slowest, hardest to recover
   from a crash.

Recommendation: option 1 (no new dependency, mirrors current architecture).

## Scope

In:
- `locked_file()` in `ai_log.py`.
- A new private `_acquire_lock(fd)` / `_release_lock(fd)` pair that
  dispatches on `sys.platform`.
- Test that exercises concurrent appenders on Windows CI.

Out:
- Lock semantics on POSIX — `fcntl.flock` stays.
- Any change to call sites; `locked_file()` is the only public surface.

## Acceptance

- On Windows, two processes appending to the same log file produce no
  interleaved bytes (concurrency test asserts every line round-trips through
  `parse_sessions()`).
- POSIX behavior is unchanged (existing test suite passes).
- No new runtime dependencies.

## Risks

`msvcrt.locking` locks byte ranges, not whole files. The shim must lock
byte 0 with a large enough length (or use `LK_LOCK` over the file size) to
behave equivalently to `flock(LOCK_EX)`. Document the choice.
