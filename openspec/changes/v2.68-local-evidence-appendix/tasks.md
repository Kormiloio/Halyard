# v2.68 — Local AI-Work Evidence Appendix: Tasks

Status: **COMPLETE 2026-05-16.** OSS-safe slice of the enterprise
-moved v2.19. Audit confirmed `render_ai_evidence_appendix`
(`invoicing.py:253`) already exists and is reused verbatim — v2.68
only adds standalone emission + a deterministic keyless self-digest.
No second renderer, no schema change, no signing (signing stays
enterprise).

- [x] `evidence.py`: `build_evidence_artifact()` (reuse renderer +
  honest footer + sha256 over canonical body) +
  `verify_evidence_artifact()` (keyless re-hash)
- [x] `cli_report.py`: `halyard evidence` command — report-style
  filters; stdout default (raw bytes, no Rich markup);
  `--out PATH` with `--force`; `--verify PATH`
- [x] Determinism: digest over canonical body only; footer +
  any wall-clock excluded from the hash (test: identical artifact
  across different `now` under `--all`)
- [x] Honest-boundary footer string; no signing/authorship/key
  language (asserted by test)
- [x] Tests: `tests/test_v268_local_evidence_appendix.py` (7 cases:
  renderer-reuse parity, deterministic digest, tamper-evident verify,
  wall-clock-excluded, privacy canary, honest-boundary, CLI
  stdout/--out/--force/--verify)
- [x] `docs/PRD-ai-work-ledger.md` + `docs/trust-model.md` updated
  (OSS unsigned self-digest vs enterprise signed appendix)
- [x] Roadmap entry in `openspec/project.md` (v2.68 = OSS slice;
  v2.19 signed stays enterprise)

## Gate
- [x] `pytest` green
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
