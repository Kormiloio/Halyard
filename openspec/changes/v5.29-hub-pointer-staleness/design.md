# v5.29 — Design

## Why `find_hub()` keeps its contract

The obvious change is to make `find_hub()` raise, or return a richer type,
when the pointer is stale. Both are wrong here.

`find_hub()` has 44 call sites across 20 modules — `db.py`,
`reports.py`, `dashboard.py`, every collector, the hub server. Almost all
follow the same shape:

```python
project_dir = find_project_dir(start=cwd) or find_hub()
```

They want one question answered: *is there a hub I can write to right now?*
For them, "never configured" and "configured but gone" are genuinely the
same answer, and both must stay non-fatal — a collector firing from a Stop
hook cannot raise at the user.

So the distinction is added *beside* the existing function, not inside it:

```python
def configured_hub_path() -> Path | None:
    """The hub path as configured, whether or not it currently exists."""
```

Only the doctor calls it. One new function, one new call site, no behaviour
change anywhere else.

## Why `hub.stale` is an error, not a warning

The v5.23 precedent is that detection-only checks stay `warning` so the
exit code keeps meaning "reports are wrong". A stale pointer is different in
kind: capture is actively degraded while it persists. Every session outside
a project directory diverts to `unattributed.log` and stops appearing in
reports, invoices, and the dashboard.

It is also trivially fixable and needs no investigation, unlike the ledger
duplicate canary, which asks the user to hunt a re-appending writer before
touching anything. `error` here is a call to action with an unambiguous
remedy.

Nothing is lost while it persists — `write_unattributed_session` is
documented as recoverable and `assign-unattributed` reclaims the rows — so
the check's detail should say that plainly. A user who sees `error` and
believes a day of telemetry is gone will do something more destructive than
repointing a file.

## Check ordering

`hub.stale` must precede the existing `hub.configured` branch, which is what
currently fires. The two are mutually exclusive: `hub.configured` keeps its
existing meaning of "no pointer at all", and `hub.stale` takes the case
where a pointer exists but does not resolve. Keeping them as separate ids
matters — the dashboard and TUI health surfaces key off check ids, and
collapsing them into one id would make the two states indistinguishable
downstream for exactly the same reason they were indistinguishable in
`find_hub()`.

## CLI shape

The setter moves to the `hub` sub-app as `hub set <PATH>`, with `hub show`
for the read side. This is not a new invention — `hub.py:9` and
`orchestration.py:396` already tell users to run `halyard hub set <path>`.
The change makes the code match its own documentation.

The bare `hub` command in `cli_setup.py` is deleted rather than renamed. It
has been unreachable since the sub-app was introduced, so nothing can depend
on it; leaving it registered would preserve the shadowing hazard for the
next command added to either module.

Registration order in `cli.py` is left alone. Reordering so `cli_setup` wins
would fix this instance and leave the trap armed — Typer silently accepts
the collision either way. Removing the duplicate name is the durable fix.

## Verification

The failure needs a pointer whose target does not exist, which no
project-fixture setup produces naturally. Tests write the pointer file
directly under a patched `Path.home()`, pointing at a `tmp_path`
subdirectory that is never created.

Note the pointer is written through `write_trusted_state` and read through
`read_global_trusted_state`; with `state_integrity` mode `off` (the default)
it is a plain file, so a bare `write_text` is sufficient for the fixtures and
avoids coupling the tests to the integrity layer.

Regression coverage for the CLI half is a direct assertion that `hub set`
exists and that no bare `hub` command shadows it — the original defect was
invisible precisely because both registrations "succeeded".
