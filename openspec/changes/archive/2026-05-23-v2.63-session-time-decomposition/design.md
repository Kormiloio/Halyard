# v2.63 — Session Time Decomposition: Design

## Phase 0 — Audit (COMPLETE 2026-05-16) — TWO BLOCKING CONFLICTS

Before any code, the data sources and existing schema were audited
against the actual collectors. Two findings invalidate the design as
written:

### Conflict 1 — `agent_active_seconds` is NOT greenfield

The design says "add `agent_active_seconds` as a derived property,
never stored/serialized." But it **already exists as a stored,
serialized, parsed field** (`ai_log.py:261`, serialized `:382`,
parsed `:695`), and is load-bearing:

- `record-session --agent-active-seconds` CLI flag writes it directly
  (`cli_session.py:423,530,581`) — a manual-capture path.
- `work_health.py` uses it for the active-ratio health check
  (`:68–82,212,260`) — `agent_active_seconds / wall_seconds <
  threshold`.
- Existing `ai-sessions.log` lines may already carry
  `agent_active_seconds=` tokens; round-trip is tested
  (`test_session_roundtrip.py`).

Converting it to a derived `api+tool` property is a **breaking
change**: it deletes a serialized field (silent data loss on read of
existing logs), removes a working CLI flag with no api/tool substitute
for manual entry, and dark-fails the work-health check (api/tool are
almost never available → property returns `None` → health check
silently stops fending). The "avoid an inconsistent third field"
rationale doesn't apply — the field predates this change and has an
independent meaning (manually/total-recorded active time).

### Conflict 2 — Gemini does not expose the API/tool split to any collector

The proposal's motivating example is the Gemini `/quit` terminal
summary (`API Time 3m25s · Tool Time 18m24s`). Audit of what Halyard
actually receives:

- **Gemini history JSON** (`gemini_history.py`): schema is
  `startTime`, `lastUpdated`, `messages[].tokens{input,output,cached,
  thoughts}`, `toolCalls[]{id,name,status}` — **no per-call duration,
  no api/tool time block**.
- **Gemini AfterModel hook**: `llm_response.usageMetadata` is token
  counts only — **no timing**.

The `/quit` split is computed and rendered by Gemini CLI internally at
quit; it is **not persisted to the history file nor delivered to any
hook**. So Gemini — the headline source — yields **no capturable
api/tool timing**. Capturing it would require estimation, an explicit
non-goal.

- **Codex** rollout JSONL *does* carry per-event timestamps with
  `*_begin`/`*_end` tool events (`codex_app.py:142,177–181`), so
  `tool_seconds` is derivable by pairing begin/end spans. `api_seconds`
  is **not** directly available (no model-call duration events;
  wall−tool would be estimation → non-goal).
- **Claude Code / Cursor** — no split (as the design already says).

### Conflict 2 — deep dive (on-disk Gemini state, 2026-05-16)

Per user request, investigated further than the schema — actual
on-disk `~/.gemini` state on this machine:

- **Chat session JSON** (`tmp/<slug>/chats/session-*.json`, the file
  `gemini_history.py` parses): top keys `sessionId, projectHash,
  startTime, lastUpdated, messages, kind`. Every `gemini` message and
  every `toolCalls[]` entry carries a single **`timestamp`** (ISO ms)
  — but **no duration, no begin/end pair, no api/tool block**. The
  `/quit` API/Tool split is computed in-memory and rendered to the
  terminal only; it is never persisted.
- **`tmp/<slug>/logs.json`** — flat list of user prompts + timestamps.
  No timing.
- **`settings.json`** has `"metrics": {"enabled": true}` but `~/.gemini/
  logs` is empty and there are **no OTEL/trace/span/collector files**
  anywhere under `~/.gemini`. Gemini CLI's structured api/tool latency
  exists only via **opt-in OpenTelemetry** (off by default, needs a
  running OTLP collector or `telemetry.outfile`), which is a different
  ingestion model entirely — out of scope for v2.63's "parse the
  session-end summary" design and a much larger separate change.

Net: a precise api-vs-tool split from per-event timestamps alone is
impossible without heuristically attributing inter-event gaps —
estimation, the change's explicit non-goal. **The Gemini door is
definitively closed for v2.63 by default.** Codex (`*_begin`/`*_end`
pairs → `tool_seconds`) remains the only buildable signal; `api_seconds`
is available from no collector.

### Audit conclusion — design must be rescoped before coding

As specced, v2.63's primary deliverable (Gemini api/tool split) is
**unbuildable from real data**, and its schema instruction (derive
`agent_active_seconds`) is a **breaking change to an existing
load-bearing field**. The buildable residue is: `tool_seconds` from
Codex begin/end spans only; `api_seconds` nowhere; keep
`agent_active_seconds` as the existing independent stored field.
Whether that residue is worth a schema bump is a product call —
**escalated to the user before implementation** (see proposal.md
status). The original schema/collector design below is retained for
historical context but is superseded by the rescope decision.

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
