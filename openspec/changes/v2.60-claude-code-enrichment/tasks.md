# v2.60 — Claude Code Collector Enrichment: Tasks

Status: **complete (1156 tests passing)**.

- [x] `_read_from_transcript()` → `_TranscriptStats` dataclass: also
  yields user-turn count, tool_use/tool_result(+error) counts,
  session_id, wall span, per-model tally (+ `model_breakdown` prop)
- [x] `handle_stop_hook()`: parse transcript whenever present (not
  only when payload lacked usage); map onto `AiSession` with
  unavailable-is-`None`; `session_id` from payload first
- [x] Log serialisation round-trips all newly-set fields (tested)
- [x] Tests: `tests/test_v260_claude_code_enrichment.py` (6 cases);
  existing `_read_from_transcript` tuple tests migrated to the
  dataclass (test_v1_collectors, test_v239)
- [x] Roadmap entry in `openspec/project.md` (item 37)

## Gate
- [x] `pytest` green (1156 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
