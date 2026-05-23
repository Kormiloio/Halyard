# v2.59 — Collector Schema-Drift Canary: Design

## Where

`src/halyard/doctor.py` only. New `_collector_drift_checks(...)`
appended in `build_doctor_report()` right after
`_unwired_tool_checks(...)`. Output is ordinary `DoctorCheck` objects
→ `render_text` / `render_json` / dashboard / TUI inherit it free.

## Signal

"Real model" reuses the existing collector rule (replicated locally so
doctor stays import-light, matching how it already inlines such
checks):

```python
_UNREAL = {"", "default"}
def _model_unreal(m: str) -> bool:
    return (not m) or m in _UNREAL or m.endswith("-unknown")
```

Per tool, over that tool's sessions sorted by `start`:

- `recent`  = last `_DRIFT_WINDOW` (= 5) sessions
- fire iff:
  - the tool has `>= _DRIFT_WINDOW` total sessions, AND
  - **every** session in `recent` has an unreal model, AND
  - **at least one** session *older* than `recent` has a real model
    (the healthy baseline — proves the tool used to capture it, so
    this is a regression not a never-worked tool)

`warning`, never `error`: capture still works, enrichment regressed —
exit-code/CI contract preserved (mirrors v2.52).

```
DoctorCheck(
  id=f"drift.{tool}",
  label=f"{tool} (collector drift)",
  status="warning",
  detail=f"last {n} {tool} sessions have no real model "
         f"(was capturing it before) — upstream format may have changed",
  fix=f"check the {tool} hook/output and the tool's version; "
      f"halyard doctor --tool <t> for hook health",
)
```

## Session source

Reuse the existing doctor session access. `build_doctor_report` already
resolves `project_dir` and `hub_dir`; `_collector_drift_checks` reads
sessions from those via `parse_sessions` (same as
`_latest_recent_session`), deduped, grouped by `session.tool`. No new
aggregation layer; if neither dir is present, the check yields nothing.

## Thresholds (module constants, tunable)

- `_DRIFT_WINDOW = 5` — recent run length and minimum-history gate.
  Small enough to notice within a day of active use, large enough that
  a couple of genuinely model-less turns don't trip it.

## Tests (`tests/test_v259_collector_drift.py`)

`monkeypatch.setattr(Path, "home", tmp)` + a tmp project log:

1. 5+ healthy `claude-code` then 5 unreal-model → one `drift.claude-code`
   warn with the documented fix.
2. Healthy throughout → no drift check.
3. Always unreal (no healthy baseline) → no check (not a regression;
   that's the v2.52 unwired/again territory, not drift).
4. Fewer than `_DRIFT_WINDOW` sessions → no check (insufficient signal).
5. Recent run mixed (4 unreal + 1 real) → no check (not *sustained*).
6. Two tools, only one drifting → exactly that tool flagged.
7. `has_errors(report)` stays False with only `drift.*` warnings
   (exit-code contract).
8. `render_json` includes the `drift.*` id.

## Gate

Full `pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry in `openspec/project.md`. One-line mention in
`current-direction.md` health-surface lineage (detection enhancement,
not a new product surface — no PRD-halyard scope change).
