# Spec: Cross-Platform File Locking

## Requirement: `locked_file()` MUST provide an OS-level exclusive lock on every supported platform.

Halyard's append paths rely on `locked_file()` to serialise writes to
`ai-sessions.log` across processes. On POSIX, this is `fcntl.flock`. On
Windows, an equivalent lock MUST be acquired before the file descriptor is
yielded to the caller and released before the file is closed.

### Scenario: POSIX behaviour is preserved

WHEN `locked_file(path, "a")` is called on Linux or macOS
THEN an `fcntl.flock(fd, LOCK_EX)` is held for the duration of the `with` block
AND the lock is released when the block exits, whether normally or via exception.

### Scenario: Windows acquires `msvcrt.locking`

WHEN `locked_file(path, "a")` is called on Windows
THEN `msvcrt.locking(fd, LK_LOCK, N)` is held for the duration of the block
WHERE `N` is large enough that any seek-and-write inside the block falls
within the locked byte range
AND the lock is released before `close()`.

### Scenario: Two processes append concurrently

WHEN two OS processes call `append_session()` against the same log file at
the same time
THEN every line in the resulting log parses cleanly via `parse_sessions()`
AND no line is interleaved with bytes from the other process
AND the lock helper does NOT depend on `sys.platform == "linux"` or
`sys.platform == "darwin"` checks at call sites.

### Scenario: Lock backend is selected once at import time

WHEN `ai_log.py` is imported
THEN the lock acquire/release functions are bound exactly once based on
`sys.platform`
AND no per-call dispatch overhead is incurred.

### Scenario: Unknown platform falls back to thread-only locking

WHEN `locked_file()` runs on a platform with neither `fcntl` nor `msvcrt`
THEN the thread-level `RLock` is still acquired
AND a one-time warning is emitted on first use to document the lack of
cross-process safety
AND no exception is raised.
