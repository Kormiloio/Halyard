# v2.62 — Cache-Aware Cost Correctness: Tasks

Status: **Phase 1 (audit) complete 2026-05-16; Phases 2–3 rescoped to
regression-proofing + documentation — no behavioural fix needed (audit
found no double-count; all four collectors already emit fresh-only
input). See design.md "Audit conclusion".**

- [x] Phase 1: audit each collector's input/cache token semantics;
  authoritative per-collector contract recorded in `design.md`.
  Finding: no double-count exists; cache_write structurally
  unavailable for Gemini/Codex (documented `None`, not dropped)
- [x] Phase 2: `normalise_input(...)` shared helper in
  `collectors/__init__.py`; gemini_cli (hook fallback),
  gemini_history (per-message), codex_app routed through it
  (`cache_inclusive=True`, behaviour-identical to prior `max(0,…)`
  math). claude_code/cursor untouched — provably exclusive
  (`cache_inclusive=False` no-op covered by test)
- [x] Phase 3: resolved to documentation — Gemini/Codex expose no
  cache-creation field; `cache_write` correctly stays `None`
  (asserted by tests, documented in PRD)
- [x] Tests: `tests/test_v262_cache_cost_correctness.py` (8 cases:
  helper contract incl. floor + no-op proof, double-count regression,
  gemini & codex gross→fresh + cache_write None, v2.61 composition)
- [x] `docs/PRD-ai-work-ledger.md`: "Token contract (v2.62)"
  subsection + documented immutable-history caveat
- [x] Roadmap entry in `openspec/project.md` updated to complete

## Gate
- [x] `pytest` green (1198 tests)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
