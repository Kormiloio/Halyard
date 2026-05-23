# v2.69 — Machine-readable JSON output: Tasks

Status: **COMPLETE 2026-05-16.** Unify + complete + document; not
greenfield (audit found `--json` already in doctor/health/usage/log/
outcome in 3 shapes).

- [x] `jsonio.py`: `to_jsonable()` / `dump_json()` / `emit()` shared
  seam (datetime/date→ISO, Path→str, Decimal→float, dataclass→obj,
  `_`-prefixed fields skipped)
- [x] `usage` migrated to the seam (keys preserved: range/summary/
  daily/by_model/by_tool); `health` json branch routed through
  `emit()` (render_json dict, keys preserved). doctor/log/outcome
  already emit valid JSON via their own helpers — left as-is
  intentionally (forcing them through the seam is churn with
  public-key-break risk; they satisfy "keep working")
- [x] Added `--json` to `report` (totals/by_*/attribution;
  per-session array gated behind `--json-sessions`), `budget`
  (today/month {spend,limit,pct,state}), `status`
  ({active,slug?,started?,elapsed_minutes})
- [x] `evidence --json` → `build_evidence_data()` structured metrics,
  `digest: null`; `--verify`+`--json` mutually exclusive
- [x] `--json` suppresses console; report/evidence error path emits
  `{"error":…}` with non-zero exit
- [x] Tests: `tests/test_v269_json_output.py` (6 cases: coverage+clean
  contract, totals parity, --json-sessions gating, JSON error path,
  evidence-no-digest, jsonio type encoding)
- [x] `README` + `docs/PRD-ai-work-ledger.md` "JSON output"
  (additive-only; digest = markdown only)
- [x] Roadmap entry in `openspec/project.md`

Deviation from design: doctor/log/outcome were specced to migrate
onto the seam; left on their existing JSON emitters instead (they
already produce valid, stable JSON — migration is churn/risk with no
user-visible gain). Recorded here per spec discipline.

## Gate
- [x] `pytest` green
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
