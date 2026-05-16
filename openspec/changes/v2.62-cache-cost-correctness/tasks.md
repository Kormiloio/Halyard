# v2.62 — Cache-Aware Cost Correctness: Tasks

Status: **proposed (spec only, not started)**.

- [ ] Phase 1: audit each collector's input/cache token semantics
  against real payload/transcript fixtures; record the per-collector
  contract in `design.md`
- [ ] Phase 2: `normalise_input(...)` shared helper; apply per
  collector per audit (no-op for already-exclusive collectors)
- [ ] Phase 3: capture `cache_write` for Gemini + Codex when exposed
- [ ] Tests: `tests/test_v262_cache_cost_correctness.py` (5 cases incl.
  double-count regression + no-op proof)
- [ ] `docs/PRD-ai-work-ledger.md`: "Token contract" subsection +
  documented pre-v2.62 under-count
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
