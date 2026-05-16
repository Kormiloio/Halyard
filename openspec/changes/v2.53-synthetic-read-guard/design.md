# v2.53 — Parse-Time Synthetic-Telemetry Guard: Design

## Predicate

`src/halyard/collectors/__init__.py`, next to `session_is_implausible`:

```python
# Exact canned payloads the thedotmack claude-mem worker-service.cjs
# daemon appends directly to ai-sessions.log (bypassing collectors).
_SYNTHETIC_FINGERPRINTS: set[tuple[int, int, str]] = {
    (2000, 400, "claude-3.5-sonnet"),
    (100, 50, "gemini-2.0-pro"),
}


def session_is_synthetic_telemetry(session: AiSession) -> bool:
    """True for the claude-mem daemon's canned, unattributed $0 rows.

    Deliberately narrow: requires the exact token pair, the exact
    legacy model string, zero cost, and no project — together
    impossible for genuine current work, so there are no false
    positives on real sessions.
    """
    if session.cost_usd != 0:
        return False
    if session.project:
        return False
    return (
        session.input_tokens,
        session.output_tokens,
        session.model,
    ) in _SYNTHETIC_FINGERPRINTS
```

`cost_usd` is a `Decimal`; `!= 0` compares cleanly against `Decimal(0)`
and `0.0`. `session.project` falsy covers `None` and `""`.

## Read-path filter (the durable fix)

`src/halyard/ai_log.py`, end of `parse_sessions`, before `return`:

```python
return [s for s in sessions if not session_is_synthetic_telemetry(s)]
```

Import is local inside the function (avoids a module import cycle:
`collectors` imports `ai_log`). Amendment folding already mutated the
first-occurrence objects in place, so filtering the final list is
correct and order-preserving.

`parse_sessions` is the single seam every surface shares — CLI
(`build_ai_report`), dashboard (`build_aggregate_dashboard_state` via
`aggregate_session_dirs` → `parse_sessions`), and the v2.50 MCP server
(`mcp_server._aggregate_sessions` → `parse_sessions`). One edit, total
coverage. No quarantine write (parse runs per render → would grow
unbounded); the raw line remains in the log, just unsurfaced.

## Write-path defence in depth

The three collector guards already read:

```python
if not session_has_evidence(session) or session_is_implausible(session):
```

Add `or session_is_synthetic_telemetry(session)` to
`claude_code.py:210`, `cursor.py:187`, `gemini_cli.py:257`. Cheap,
keeps Halyard's own collectors from ever emitting the fingerprint.

## Tests (`tests/test_v253_synthetic_read_guard.py`)

1. The two exact fingerprints → predicate True.
2. Same token pair but **nonzero cost** → False (real work).
3. Same token pair but **attributed project** → False.
4. Same tokens, **current model** (`claude-opus-4-7`) → False.
5. Genuine session (real tokens/cost/project) → False.
6. `parse_sessions` on a log mixing 2 synthetic + 2 real rows →
   returns only the 2 real; the raw synthetic lines remain in the
   file on disk (assert file text unchanged / still 4 `s` lines).
7. Aggregate/MCP path (`mcp_server._aggregate_sessions` or
   `build_aggregate_dashboard_state`) excludes synthetic, proving the
   single-chokepoint claim end to end.
8. Collector write guard: feeding a synthetic-fingerprint stop payload
   writes nothing (mirror an existing collector test).

Reuse `tests` helpers: `_proj`, `AiSession`, `append_session`,
`parse_sessions`.

## Gate

Full `pytest` + `ruff check` + `ruff format --check` + `mypy src/`.
Roadmap entry (item 32, v2.19 → 33) status complete with new count.
