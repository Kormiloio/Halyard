# Spec: Claude Code Collector Enrichment

## Requirement: Populate available rich fields

When the Claude Code Stop payload (and/or its transcript) provides a
value, the written `AiSession` MUST carry it: `session_id`,
`user_message_count`, `tool_calls`, `tool_errors`, `wall_seconds`,
and `model_breakdown` (multi-model sessions).

### Scenario: full transcript
- GIVEN a Stop payload with a transcript containing user turns, 5
  `tool_use` events (1 erroring), spanning 8 minutes
- WHEN the Stop hook runs
- THEN the session has `tool_calls=5`, `tool_errors=1`,
  `user_message_count` = the user-turn count, `wall_seconds≈480`,
  and a non-null `session_id`.

### Scenario: multi-model session
- GIVEN a transcript whose events used two distinct models
- THEN `model_breakdown` is set (`"<m1>:<n1>|<m2>:<n2>"`).

## Requirement: Unavailable is not zero

A field MUST be `None` when the source does not provide it, and `0`
only when the source genuinely shows none.

### Scenario: payload-only (no transcript)
- GIVEN an older Stop payload with `usage` but no `transcript_path`
- THEN `tool_calls`, `tool_errors`, `user_message_count`,
  `wall_seconds`, `session_id` are all `None` (not `0`/`""`), and the
  existing token/model/cost behaviour is unchanged.

### Scenario: no accept signal
- GIVEN the payload exposes no explicit suggestion-accept tally
- THEN `accepted_suggestion_count` is `None` — never inferred.

## Requirement: Backward compatibility

Existing `ai-sessions.log` lines without these tokens MUST parse
identically; newly written lines MUST round-trip
(`parse_sessions` → equal session). No `AiSession` schema change.

## Requirement: Privacy boundary

Only ids, counts, and durations are captured. No prompt, code, or
transcript text is written to the ledger.
