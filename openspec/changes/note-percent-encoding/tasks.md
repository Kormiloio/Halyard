# Tasks: Percent-Encoding for Free-Text Log Fields

## Implementation

- [x] Add `_encode_free_text(value)` and `_decode_free_text(value)` helpers
  in `ai_log.py`. Encoder: `urllib.parse.quote(value, safe="")`. Decoder:
  if `%` in value → `urllib.parse.unquote(value)`, else
  `value.replace("_", " ")` (legacy fallback).
- [x] Replace inline `note` encoding in `AiSession.to_log_line()` with
  `_encode_free_text(self.note)`.
- [x] Replace inline `resume_command` encoding in `to_log_line()` with
  `_encode_free_text(self.resume_command)`.
- [x] In `_parse_line_result()` (or wherever `note` and `resume_command`
  are decoded), call `_decode_free_text()` for both fields.

## Tests

- [x] Round-trip: literal underscore survives encode → write → parse → decode.
- [x] Round-trip: percent sign survives.
- [x] Round-trip: unicode codepoint survives.
- [x] Read legacy underscore-encoded `note` (no `%`) still decodes to spaces.
- [x] `session_hash` of a pre-change line is unchanged after the patch.
- [x] Quarantine still fires for actually-malformed lines.

## Verification

- [x] `uv run pytest tests/` — all green.
- [x] `uv run ruff check .` — clean.
- [x] `uv run mypy src/halyard/ai_log.py` — clean.
