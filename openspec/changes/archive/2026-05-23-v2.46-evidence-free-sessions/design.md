# v2.46 — Suppress Evidence-Free Collector Sessions: Design

## The predicate

A shared notion: a session has **evidence of a real turn** if ANY of:

- `tokens_available` is True (input or output tokens > 0), or
- cache tokens > 0, or
- a history summary was parsed (gemini only), or
- `tool_calls` or `tool_errors` is truthy, or
- any interaction count is truthy (interaction/user/assistant/prompt/
  accepted/rejected), or
- `code_added` / `code_removed` / `files_touched_count` is truthy, or
- `commit_count` is truthy, or
- a real model was identified (not "", not the `*-unknown` sentinel).

If **none** hold, the hook fired without a turn → skip the append.

The check is applied **just before the append**, after all enrichment
is resolved (so history/tool/interaction signals are known), using the
already-built `AiSession` plus the gemini `history_summary` flag. A
small helper `_session_has_evidence(session, *, history=False)` in each
collector (or a shared helper in `collectors/__init__` if clean) keeps
it readable and identically applied.

## Gemini (`handle_agent_stop`)

After the `AiSession` is constructed, before the
`append_session` / `write_unattributed_session` branch:

```
if not _session_has_evidence(session, history=history_summary is not None):
    _reset_state()           # same cleanup the normal path does
    return 0
```

## Cursor (`handle_stop_hook`)

Same shape before its append/unattributed branch; `history=False`
(cursor has no history file). `_clear_session_start()` is already called
earlier, so just return 0 without appending.

## Why "model identified" counts as evidence

A turn that produced a model name but somehow zero tokens (e.g.
provider omitted usage) is still a real turn worth recording with
`tokens_available=false`. Only the truly empty fire (unknown model AND
no tokens AND no signals) is dropped — that is unambiguously "nothing
happened."

## Tests

`tests/test_evidence_free_sessions.py`:
- gemini: AfterAgent with empty state (no model, 0 tokens, no history,
  no payload signals) → **no** line appended, state file cleared,
  returns 0;
- gemini: AfterAgent with output tokens > 0 → session appended (control);
- gemini: AfterAgent with 0 tokens but tool_calls in payload → appended
  (signal present);
- cursor: stop with empty payload → no line appended;
- cursor: stop with input_tokens > 0 → appended (control);
- cursor: stop with 0 tokens but interaction_count > 0 → appended.

Drive via the existing collector test patterns (stdin payload + tmp
project dir), assert on the project log contents.

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
