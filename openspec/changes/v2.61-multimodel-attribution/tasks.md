# v2.61 — Multi-Model Session Attribution: Tasks

Status: **complete (1168 tests passing)**.

- [x] New `halyard.model_breakdown`: `ModelSeg`, `encode`/`parse`
  (usage form; legacy `model:count` & truncation → `None`),
  `cost_of` (Σ), `primary_model`, `iter_model_usage`
- [x] `ai_log._safe_breakdown` — serialise `model_breakdown` without
  the 128-char cap (multi-model strings survive intact)
- [x] `usage._model_buckets` + `mcp_server._cost_by_model`: per-model
  attribution when breakdown present; single-model path byte-identical
  (dashboard model table inherits via `_model_buckets`)
- [x] Claude collector: `_TranscriptStats.model_usage` → usage-form
  `model_breakdown` + `primary_model`; cost = Σ when multi-model
- [x] Gemini collector: `_format_model_breakdown` → usage form;
  primary + Σ cost when multi-model
- [x] Tests: `tests/test_v261_multimodel_attribution.py` (13 cases:
  encode/parse, legacy/truncation safety, Σ-cost, rollups, long
  round-trip); v2.60 breakdown test migrated to usage form
- [x] Roadmap entry updated in `openspec/project.md` (item 38)

Cursor/Codex are single-model in practice → no breakdown emitted (the
single-model path is provably unchanged); documented, not faked.

## Gate
- [x] `pytest` green (1168 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
