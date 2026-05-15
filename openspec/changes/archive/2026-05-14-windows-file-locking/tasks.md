# Tasks: Windows-Compatible File Locking

## Implementation

- [x] Add a `_acquire_lock(fd)` / `_release_lock(fd)` pair in `ai_log.py`
  that dispatches once at import time on `sys.platform`.
- [x] Bind the POSIX path to `fcntl.flock(fd, LOCK_EX)` / `fcntl.flock(fd, LOCK_UN)`.
- [x] Bind the Windows path to `msvcrt.locking(fd, LK_LOCK, N)` /
  `msvcrt.locking(fd, LK_UNLCK, N)` with `N = 0x7FFFFFFF`.
- [x] Bind the fallback to no-op acquire/release plus a one-time `warnings.warn()`.
- [x] Refactor `locked_file()` to call `_acquire_lock` / `_release_lock`
  inside the `try` / `finally`, dropping the inline `_fcntl` check.

## Tests

- [x] Unit test: on the current platform, `_acquire_lock` and `_release_lock`
  are bound to non-`None` callables.
- [x] Unit test: `locked_file()` releases the lock even if the caller raises
  inside the `with` block (use a mock acquire/release pair).
- [x] Integration test: existing concurrent-append tests still pass.

## Docs

- [x] Note in `ai_log.py` module docstring that file locking is
  cross-platform.

## Verification

- [x] `uv run pytest tests/` — all green.
- [x] `uv run ruff check .` — clean.
- [x] `uv run mypy src/halyard/ai_log.py` — clean.
