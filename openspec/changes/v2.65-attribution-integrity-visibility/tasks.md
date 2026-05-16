# v2.65 — Attribution Integrity & Visibility: Tasks

Status: **proposed (spec only, not started)**.

Phase A — capture + surface (shippable alone):
- [ ] Widen `attr_method` at the inference site: `repo-map` / `toml` /
  `git-auto` instead of the catch-all `git` (collectors +
  `infer_project` path); back-compat map legacy `git` → `auto`
- [ ] `src/halyard/attribution.py`: `attribution_confidence(session)`
  + `attribution_mix(sessions)`
- [ ] Surface the mix: `halyard report` line, dashboard attribution
  panel chip, MCP `work_summary.attribution_mix`

Phase B — detect + remediate:
- [ ] `doctor._attribution_quality_checks`: adrift-rate regression +
  per-remote regression (`warning`, v2.59 pattern)
- [ ] Upgrade the `state.unattributed` doctor `fix` to emit exact
  per-remote `link-repo`/`adopt` commands (propose only)

Cross-cutting:
- [ ] Tests: `tests/test_v265_attribution_integrity.py` (8 cases:
  rung capture, confidence/legacy, mix, canary, exit-code contract,
  remediation-no-write, MCP surface)
- [ ] `docs/PRD-halyard.md` trust-label concept extended;
  `current-direction.md` one-line note
- [ ] Roadmap entry in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
