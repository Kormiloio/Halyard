# v2.60 — Claude Code Collector Enrichment: Tasks

Status: **proposed (spec only, not started)**.

- [ ] Extend `_read_from_transcript()` to also return user-turn count,
  tool_use/tool_result(+error) counts, session_id, wall span, and a
  per-model tally
- [ ] `handle_stop_hook()`: map those onto `AiSession` fields with
  unavailable-is-`None` semantics; `session_id` from payload first
- [ ] Verify log serialisation round-trips all newly-set fields
- [ ] Tests: `tests/test_v260_claude_code_enrichment.py` (6 cases)
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
