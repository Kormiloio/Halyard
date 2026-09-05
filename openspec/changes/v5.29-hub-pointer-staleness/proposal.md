# v5.29 — Stale hub pointer is silent, and its documented fix does not exist

## Why

A live capture outage on the maintainer's machine, diagnosed 2026-09-03.
Every Claude Code session for a day landed in `~/.halyard/unattributed.log`
instead of a ledger — 12 sessions — and `halyard doctor` reported the cause
as `no hub configured`, which was false. A hub *was* configured. Its
directory had been moved.

Two independent defects combined to make a one-line config problem
undiagnosable.

### 1. `find_hub()` collapses "unconfigured" and "vanished" into `None`

`~/.halyard/hub` is a pointer file holding an absolute path. `find_hub()`
ends:

```python
# src/halyard/hub.py:55
return path if path.is_dir() else None
```

So a pointer at a directory that no longer exists is indistinguishable from
no pointer at all. That is the right contract for the 44 call sites that
just want a usable hub, but it is exactly wrong for the doctor, whose job is
to explain *why* capture is failing.

The consequence is silent and data-diverting. In
`collectors/claude_code.py:423`:

```python
project_dir = find_project_dir(start=cwd) or find_hub()
can_append_project_log = project_dir is not None and (project_dir / AI_LOG_FILENAME).exists()
```

`find_project_dir` is a pure CWD walk-up for `halyard.toml`; `find_hub()` is
the only fallback. When the pointer goes stale, every session outside a
project directory silently diverts to `unattributed.log`. Nothing is lost —
the log is explicitly recoverable — but the user is told the wrong thing
about why, and the sessions stop appearing in reports.

The real pointer in the incident read:

```
/Users/…/GoogleDrive-…/My Drive/Documents/Development
```

The directory had been reorganised away months earlier. Halyard tracks these
locations by absolute path, so any folder move breaks them, and nothing
notices.

### 2. `halyard hub <path>` — the advertised fix — is unreachable

`doctor` emits `fix: halyard init --hub or halyard hub <path>` (twice:
`doctor.py:134`, `doctor.py:189`). That command cannot run.

`cli_setup.register(app)` (`cli.py:86`) registers `hub` as a plain command
that sets the hub directory. `cli_hub.register(app)` (`cli.py:91`) then
registers a Typer **sub-app** also named `hub`, for daemon management. The
sub-app wins:

```
$ halyard hub /path/to/project
No such command '/path/to/project'.

$ halyard hub -h
Commands:  start   Start the Halyard Hub daemon.
           status  Check if the Halyard Hub is reachable.
```

So the user is handed a remediation that errors out, for a diagnosis that is
already wrong. The setter in `cli_setup.py:44` is dead code.

Notably, two places in the tree already document the *intended* shape —
`hub.py:9` ("Set it with `halyard init --hub` or `halyard hub set <path>`")
and `orchestration.py:396` ("Run halyard hub set <path> first") — but
`hub set` was never implemented. The docstrings describe a command that does
not exist; the command that does exist is shadowed.

## What

**1. Expose the configured-but-missing state.** Add
`configured_hub_path()` to `hub.py`, returning the pointer's target
regardless of whether it resolves. `find_hub()` keeps its contract
unchanged — 44 call sites depend on `None` meaning "no usable hub", and
widening that would push error handling into every one of them.

**2. Teach the doctor the difference.** `_hub_checks` gains a distinct
`hub.stale` check: when `find_hub()` is `None` but `configured_hub_path()`
is not, report the configured path, say it no longer exists, and state the
consequence — sessions are diverting to `unattributed.log`. `error`, not
`warning`: capture is silently degraded.

**3. Implement `hub set` / `hub show` and delete the shadowed command.**
Move the directory setter from `cli_setup.py` into the `cli_hub` sub-app,
matching the shape `hub.py` and `orchestration.py` already document. Update
both `doctor` fix strings and `docs/troubleshooting.md` (two occurrences of
the broken form).

## Out of scope

- **Auto-healing a stale pointer.** Tempting — search the registry or the
  parent of the old path for a directory with `halyard.toml` — but a hub
  holds billing-relevant ledgers and guessing wrong silently writes
  sessions into the wrong project. Detect and report; let the user repoint.
- **Making these paths relocation-proof.** The registry
  (`~/.halyard/projects`) has the identical failure mode and had its own
  dead entry in the same incident. A content-addressed or
  marker-file-based scheme would fix the class; that is a much larger
  design change and belongs in its own proposal.
- The registry's stale entries are only *detected* here insofar as doctor
  already reports them; no new registry checks in this change.
