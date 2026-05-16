# v2.49 — Require a Recorded Session Start: Design

## Cursor (`collectors/cursor.py handle_stop_hook`)

At the top of `handle_stop_hook`, before any work:

```python
if not _CURSOR_SESSION_FILE.exists():
    return 0
```

`record_session_start` (beforeSubmitPrompt) creates the file and is
idempotent for the session's life; `handle_stop_hook` clears it at the
end. So at a real stop the file is present; a stop with no prior
beforeSubmitPrompt has no file → skip. Nothing else changes (the
existing evidence + implausibility guards still apply afterwards).

## Gemini (`collectors/gemini_cli.py handle_agent_stop`)

`state = _read_state()` already returns `None` when `~/.halyard/
gc-session` is absent (SessionStart never ran). Add, immediately after
the existing `state = _read_state()` in `handle_agent_stop`:

```python
if state is None:
    return 0
```

This precedes the stale-guard/enrichment; a missing gc-session means no
SessionStart, so the AfterAgent fire is not a real turn.

## Why this is safe

Real Cursor always fires `beforeSubmitPrompt` (→ `cursor-session`)
before `stop`; real Gemini always fires `SessionStart` (→ `gc-session`)
before `AfterAgent`. The state file is therefore present for every
genuine turn. The only fires it removes are stop/AfterAgent invocations
with no recorded start — exactly the daemon's synthetic pattern.

Claude Code is intentionally untouched: it is not the synthetic target
and its evidence guard (v2.47) already covers it; tightening it risks
its transcript-based real sessions.

## Tests

`tests/test_v249_require_session_start.py`:
- cursor stop with **no** `cursor-session` file + a token-bearing
  payload → no session written, returns 0;
- cursor stop **with** a recent `cursor-session` file + same payload →
  session written (control);
- gemini AfterAgent with **no** `gc-session` → nothing, returns 0;
- gemini AfterAgent **with** a recent gc-session + tokens → written.

Existing cursor/gemini collector tests already seed the state file
(post-v2.48 fixture work) so they keep passing; any that don't are
updated to reflect the real two-phase lifecycle.

Full `pytest`+`ruff`+`ruff format --check`+`mypy` before commit.
