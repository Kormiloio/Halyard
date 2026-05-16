# v2.61 — Multi-Model Session Attribution: Tasks

Status: **proposed (spec only, not started)**. Depends on v2.60.

- [ ] Generalise `model_breakdown` grammar to `model:in/out/cr/cw`
  segments; parser tolerates legacy `model:count`
- [ ] `calculate_session_cost` (or `calculate_cost` wrapper): sum over
  segments when present, else unchanged single-model path
- [ ] Write-time `session.model` = highest-cost segment
- [ ] Shared `iter_model_usage(session)`; route `usage._model_buckets`,
  `mcp_server._cost_by_model`, dashboard model table through it
- [ ] Collector tallies: Cursor + Codex (new), Claude (upgrade v2.60),
  Gemini (count → usage form)
- [ ] Tests: `tests/test_v261_multimodel_attribution.py` (6 cases)
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
