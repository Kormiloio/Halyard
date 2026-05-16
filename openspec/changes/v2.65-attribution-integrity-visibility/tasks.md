# v2.65 — Attribution Integrity & Visibility: Tasks

Status: **complete (1185 tests passing)**.

Phase A — capture + surface:
- [x] `git_context.infer_project_with_source()` returns (slug, rung)
  `toml`/`repo-map`/`git-auto`; `infer_project` delegates (back-compat)
- [x] Claude + Gemini collectors record the specific rung in
  `attr_method` (replaces catch-all `git`)
- [x] `src/halyard/attribution.py`: `attribution_confidence`,
  `attribution_mix`, `format_attribution_mix` (legacy `git`→`auto`,
  `ws_root`→`mapped`, no project→`none`)
- [x] Surface: `halyard report` Attribution line; dashboard voyage
  Attribution column; MCP `work_summary.attribution_mix`

Phase B — detect + remediate:
- [x] `doctor._attribution_quality_checks`: adrift-rate regression +
  per-remote regression (`warning`, v2.59 pattern, exit-code safe)
- [x] `state.unattributed` fix emits exact per-remote
  `halyard link-repo … --remote …` (proposes; doctor writes nothing)

Cross-cutting:
- [x] Tests: `tests/test_v265_attribution_integrity.py` (17 cases);
  two existing collector tests migrated to `infer_project_with_source`
- [x] `docs/PRD-halyard.md` trust-label concept extended;
  `current-direction.md` Governing Principles note added
- [x] Roadmap entry status in `openspec/project.md` (item 42)

## Gate
- [x] `pytest` green (1185 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
