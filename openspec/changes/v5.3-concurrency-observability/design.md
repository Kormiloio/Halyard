# Design — v5.3 Concurrency + observability hardening

## #1 Reader shared lock

### Mechanism
`read_locked_file(path)` mirrors `locked_file` but acquires a **shared** lock:
- POSIX: `fcntl.flock(fd, LOCK_SH)` via `_acquire_read_lock`.
- Windows: no-op — `msvcrt.locking` has no shared mode; readers behave as
  before (this matches the existing writer-lock platform caveat in the module
  docstring, and torn reads are not a correctness risk for the single-user
  Windows case).
- No-fcntl fallback: no-op with the existing one-time warning.

`_iter_log_lines` was refactored to take an open file handle instead of a path,
so the caller (`parse_sessions`, `unattributed_log_count`) owns the
lock-and-open scope via `read_locked_file`.

### Why no deadlock
`read_locked_file` and `locked_file` share the per-path in-process
`threading.RLock`, then take the OS lock. The two never interleave in a single
thread on the same path: parse never writes the log it is reading (collapse is
in-memory; in-place rewrites are `adopt`-only), and `_write_quarantine` targets
a *different* file (`quarantine.log`), so there is no SH-then-EX-on-same-path
sequence that could deadlock under flock.

### Lock-hold cost
The shared lock is held for the whole parse. A ~500-line log parses in
single-digit ms, so a concurrent appending hook waits trivially; the bound is
algorithmic, not a fixed sleep.

### Honest scope
This closes a **torn-read** window, not a data-loss bug. The reviewer's
"permanently quarantines valid data" claim is false: `_write_quarantine`
appends a copy to `~/.halyard/quarantine.log` and never mutates the
append-only ledger, so the writer's complete line survives and the next parse
reads it. The fix removes the spurious quarantine entry / transient blink, and
hardens the read path as defense-in-depth.

## #2 Diagnostic log

`log_diagnostic(msg, *, tool=None, project=None)` appends
`"[utc-iso] [tool] [project] msg\n"` to `~/.halyard/diagnostic.log`, creating
the parent dir, swallowing `OSError` (we cannot log a logging failure). It is
deliberately separate from the audit `halyard.log` (which carries full
tracebacks via `_log_error`): diagnostics are one-line "why did we degrade"
breadcrumbs, not exceptions. Wired into:
- `hub_client._request` — on every `OSError/HTTPException/UnicodeDecodeError`
  that degrades the call to `None`.
- `git_context` — every subprocess `TimeoutExpired/OSError/FileNotFoundError`
  path (all funcs, not just one).

## #3 Latency regression test

A real `HubServer` is started with its `do_POST` wrapped to `sleep(0.3)` —
double the 150 ms client timeout. `append_session` (Hub-first) therefore times
out in `hub_client._request`, logs the diagnostic, returns `None`, and falls
back to the local `locked_file` write. The test asserts all three: local line
written, `"hub_client: request failed"` and `"timed out"` in the diagnostic.

## Test isolation note

`_HALYARD_DIAG_LOG` is an import-time module constant bound to the real home;
conftest only isolates `registry.REGISTRY_PATH`. So every test that touches the
diagnostic log monkeypatches `ai_log._HALYARD_DIAG_LOG` to a `tmp_path` file —
no test reads or writes the user's real `~/.halyard/diagnostic.log`. The
shared-lock test uses a real subprocess (not a thread) so the lock is exercised
through the OS flock rather than the in-process `threading.RLock`; its wait
assertion is a *lower* bound (`> 0.3s`), which instrumentation can only inflate,
so it never flakes downward (and is not the forbidden `< literal` upper bound).

## Rejected (review items)

- **Raise the 150 ms loopback timeout to 500 ms–1 s** — the timeout is a
  deliberate fail-fast to a guaranteed-correct local write; raising it makes
  every hook/UI call hang longer when the Hub is down. Kept at 150 ms.
- **Replace `_no_real_hub` with always-real Hub tests** — `_no_real_hub` is
  correct hermeticity (a dev's running Hub must not hijack unit tests); five
  test files already opt into a real `HubServer` via `HALYARD_HUB_PORT`. We
  added the missing *latency* case, not a wholesale removal.
