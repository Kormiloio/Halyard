# v2.47 — Extend Evidence-Free Guard to Claude Code: Design

## Change

In `collectors/claude_code.py handle_stop_hook`, immediately before the
`append_session` / `write_unattributed_session` branch, add:

```python
if not session_has_evidence(session):
    return 0
```

`history=False` (Claude Code has no separate history-summary flag; its
transcript enrichment already sets `interaction_count` /
`assistant_message_count` / tokens, which the predicate covers). Import
the shared helper: `from halyard.collectors import session_has_evidence`.

Placed before the append so the auto-timer-update and dashboard-hint
side effects (which follow the append) are also skipped for an empty
fire — correct, since nothing happened. The budget check and
`record_session_start` are upstream and untouched.

## Why this is safe

A real Claude Code turn reaches Stop with transcript enrichment:
`telemetry_source="claude-code-transcript"`, a real model, tokens, and
`assistant_message_count`/`interaction_count`. Any one of those makes
`session_has_evidence` return True → recorded unchanged. Only the
`claude-unknown 0 0 $0`, no-interaction, no-tool, no-code,
`telemetry_source="claude-code-hook"` stub (transcript resolution
failed AND nothing else happened) is skipped — that is unambiguously
"the hook fired but there was no turn."

## Tests

`tests/test_claude_code_evidence.py`:
- Stop with no transcript / unknown model / 0 tokens / no signals →
  **no** session appended, returns 0;
- Stop with a real model + tokens → appended (control);
- Stop with 0 tokens but interaction/assistant counts present (real
  transcript, cheap turn) → appended (the must-not-drop case).

Reuse the existing `test_v1_collectors` claude-code scaffolding
(stdin payload + tmp project). Predicate-level coverage already exists
in `test_evidence_free_sessions.py`.

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
