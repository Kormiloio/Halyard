# v2.60 — Claude Code Collector Enrichment: Design

## Where

`src/halyard/collectors/claude_code.py` — `handle_stop_hook()` and the
`_read_from_transcript()` helper. No schema changes; no other module.

## Sources available

`handle_stop_hook` already reads two things:

1. **`payload`** (stdin JSON from the Stop hook): `usage`, `model`,
   `transcript_path`, and — to confirm — `session_id`.
2. **transcript JSONL** (`payload["transcript_path"]`, Claude Code
   ≥2.x): already parsed by `_read_from_transcript()` for model,
   tokens, cache, branch, `assistant_message_count`. The same JSONL
   stream carries user turns, `tool_use` / `tool_result` events
   (incl. error results), per-event model, and per-event timestamps.

So enrichment is mostly *extracting more from a stream we already
read once* — no extra I/O, no new format coupling.

## Mapping (capture only what's present; else `None`)

| `AiSession` field | Source | Rule |
|---|---|---|
| `session_id` | `payload.get("session_id")` → else transcript header | `None` if absent |
| `user_message_count` | count of `role=="user"` transcript entries since `start` | `None` if no transcript |
| `tool_calls` | count of `tool_use` events | `None` if no transcript |
| `tool_errors` | count of `tool_result` with `is_error` true | `None` if no transcript |
| `wall_seconds` | last_ts − first_ts in the session window, ints | `None` if <2 timestamps |
| `accepted_suggestion_count` | only if the payload/transcript exposes an explicit accept signal | else `None` (do **not** infer) |
| `model_breakdown` | per-`model` event tally → `"m-a:3\|m-b:1"` | single model → `None` (v2.61 generalises) |

`_read_from_transcript()` returns a dataclass/namedtuple today
(`t_model, t_in, t_out, t_cr, t_cw, t_branch, t_assistant_count`).
Extend it to also return `user_count, tool_calls, tool_errors,
session_id, wall_seconds, model_tally`. Update the single call site.

## Semantics

- **Unavailable is not zero** is the hard rule. `0` is only written
  when the stream genuinely shows zero (e.g. a session with no tool
  calls → `tool_calls=0` is truthful; a session with no transcript →
  `tool_calls=None`). This distinction already exists in the codebase
  (v2.32) and the predicates rely on it.
- `accepted_suggestion_count` is **not** synthesised from heuristics.
  Claude Code's Stop payload does not currently expose an in-session
  accept/reject tally the way Cursor does; if absent it stays `None`
  and is documented as a known limitation, not faked.
- Serialisation already supports every field (`AiSession` → log line
  emits the key=value tokens; parser already reads them). Verify the
  round-trip in tests rather than touching the serializer.

## Tests (`tests/test_v260_claude_code_enrichment.py`)

Drive `handle_stop_hook` with a synthetic payload + a temp transcript
JSONL fixture:

1. Full transcript → `session_id`, `user_message_count`,
   `tool_calls`, `tool_errors`, `wall_seconds` populated and correct.
2. `tool_result` with `is_error` → counted in `tool_errors`.
3. No transcript (old payload-only format) → those fields `None`,
   not `0`; existing token/model behaviour unchanged (regression).
4. Multi-model transcript → `model_breakdown` set; single-model → `None`.
5. Log round-trip: written line re-parses to an equal session.
6. v2.59 drift canary still fires if `model` regresses (no interaction
   with the new fields).

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap entry.
Bug-class enrichment (spec-exempt by rule, but specced because the
user asked for the full set up front).
