# v5.31 — A lost hub response reports a successful start as a failure

## Why

Surfaced as a Windows CI flake on PR #9 that "passed on re-run". It is not
a flake in the test; it is a real race in `start_timer`, and Windows only
makes it likely enough to catch.

`tests/test_v42_hub_state.py::test_library_timer_calls_delegate_to_hub_then_stop`
failed with:

```
halyard.orchestration.TimerAlreadyRunning: Timer already running for 'acme:auth'. Stop it first.
```

on a fresh per-test `home`, where no timer could plausibly have been left
over — alongside, in the same run:

```
ConnectionAbortedError: [WinError 10053] An established connection was aborted
  File "...\halyard\hub_server.py", line 1107, in _respond_error
```

The two are the same event. The chain, verified end to end in the code:

1. **The hub commits before it responds.** In
   `hub_server._handle_timer_action`, `start_timer(target_dir, project,
   direct=True)` writes the timeclock clock-in line and `~/.halyard/active`,
   then the in-memory `hub.state` is updated and events emitted — and only
   after all of that is the HTTP response written.
2. **The response is lost.** `_respond_json` / `_respond_error` raise
   `ConnectionAbortedError` if the peer has gone away.
3. **The client cannot tell.** `hub_client._request` returns `None` on any
   connection failure, so `hub_client.start_timer` returns `None`, so
   `_try_start_timer_via_hub` returns `None`.
4. **The fallback trips over the hub's own write.** `start_timer` falls
   through to `_start_timer_local`, which re-reads
   `read_active_timer(prefer_hub=False)` inside the timeclock lock, finds
   the active file the hub wrote in step 1, and raises
   `TimerAlreadyRunning`.

So the user runs `halyard start acme:auth`, the timer **does** start, and
they are told:

> Timer already running for 'acme:auth'. Stop it first.

The advice is wrong twice over: the command succeeded, and the timer it
names is the one it just created. A user who follows the advice stops the
work they meant to start.

This is the same defect shape as v5.29 and v5.30: two distinct states
collapsed into one indistinguishable value. `find_hub()` returned `None`
for both "unconfigured" and "vanished". `cli_mcp` reported both "SDK
absent" and "SDK wrong-major" as "not installed". Here `_request` returns
`None` for both "hub was never reachable" (nothing happened) and "hub
committed, response lost" (everything happened).

## What

`start_timer` gains one reconciliation step between the hub attempt and
the local fallback: when the hub returns an unknown outcome, **ask the hub
what it actually did**.

`_adopt_timer_committed_by_hub` calls `hub_client.read_state()` on a fresh
connection. It adopts the committed timer only when both hold:

- the hub is reachable and reports our slug as the active project, and
- the on-disk active timer agrees.

The returned `ActiveTimer` carries the timer's **real** `started` and
`elapsed_minutes` from disk, not a synthesised "just started now", so a
user who was actually joined to a pre-existing timer sees its true age.

If the hub does not answer, nothing changes: we fall through to
`_start_timer_local` exactly as before, and a stale active file from a
crashed run still raises `TimerAlreadyRunning`. That is deliberate — an
unreachable hub cannot vouch for anything, and silently adopting an
orphaned file would be a worse failure than the one being fixed.

## Out of scope

- **Making the hub respond before committing.** That would trade this bug
  for a worse one: a lost response would then mean the user was told the
  timer started when it had not. Commit-then-respond is the right order
  for a state daemon; the client just has to reconcile.
- **Distinguishing "sent but no response" from "never connected" in the
  transport.** That is the most general fix — `_request` could report
  three outcomes instead of two — but it touches every hub call site
  (`ingest_line`, `check_collisions`, `update_presence`, `stop_timer`) and
  each needs its own reconciliation policy. `start_timer` is the one that
  currently produces a wrong, actionable-but-harmful error message.
- `stop_timer` has the mirror-image race (hub clears state, response lost,
  local fallback reports `was_running=False`). It is less harmful — the
  timer really is stopped and the user is told nothing happened — but it
  is real, and is left for a follow-up rather than widened into here.
