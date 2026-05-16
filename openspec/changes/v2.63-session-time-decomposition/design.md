# v2.63 — Session Time Decomposition: Design

## Schema

`AiSession` (`ai_log.py`): add

```python
api_seconds: int | None = None
tool_seconds: int | None = None

@property
def agent_active_seconds(self) -> int | None:
    if self.api_seconds is None or self.tool_seconds is None:
        return None
    return self.api_seconds + self.tool_seconds
```

Serialization: emit `api_seconds=`/`tool_seconds=` tokens only when
not `None` (consistent with every other optional field). Parser:
two new `case` arms reading ints. Old lines: fields stay `None`.
`agent_active_seconds` is a property — never serialized, never parsed.

## Collectors

- **Gemini** — the session-end usage/summary block carries API and
  tool time; parse to whole seconds.
- **Codex** — rollout JSONL: if event timing allows summing model vs
  tool spans, populate; else `None`.
- **Claude Code, Cursor** — no documented API/tool split in the
  payload today ⇒ both `None`. Documented as a known limitation, not
  faked. (If a future payload exposes it, wire it then; the v2.59
  drift canary covers model regressions, not these.)

## Surface

Read-only display, no new panel required:

- Reports / dashboard session detail: an "active Xm (API a · tool b)"
  line when `agent_active_seconds is not None`.
- `mcp_server`: include `api_seconds`/`tool_seconds` in the `sessions`
  tool output (metadata only — already the contract).

No aggregate metric or score in this change.

## Tests (`tests/test_v263_time_decomposition.py`)

1. Gemini fixture with API/tool time → fields set;
   `agent_active_seconds` = sum.
2. Only one part present → `agent_active_seconds` is `None`.
3. Collector with no timing (Claude/Cursor fixture) → both `None`,
   `wall_seconds` unaffected.
4. Round-trip: write → `parse_sessions` → equal session; old line
   without the tokens parses (both `None`).
5. `mcp_server.sessions` exposes the two fields.

## Docs

`docs/PRD-ai-work-ledger.md` "What Is Captured" list gains
`api_seconds` / `tool_seconds` (derived agent-active noted).

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap entry.
Feature changeset (new schema) — full spec, not bug-class.
