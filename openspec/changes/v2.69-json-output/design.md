# v2.69 — Machine-readable JSON output: Design

> Spec only — proposed. Awaiting alignment before code.

## Audit (what exists — do not rebuild)

| Command | `--json` today | Shape |
|---|---|---|
| `doctor` | yes | `doctor.render_json()` → str |
| `health` | yes | `work_health.render_json()` → dict |
| `usage` | yes | inline `asdict(analytics…)` in cli_report |
| `log` | yes | ad-hoc (`cli_session.py:21`) |
| `outcome` | yes | ad-hoc (`outcomes.py:50`) |
| `report` | **no** | — (flagship gap) |
| `budget` | **no** | — (CI spend-gate gap) |
| `status` | **no** | — (statusline gap) |
| `evidence` | **no** | markdown artifact only |

## Shared seam — `jsonio.py`

```python
def to_jsonable(obj: Any) -> Any:
    # dataclass → dict (recursive), datetime → .isoformat(),
    # date → .isoformat(), Path → str, Decimal → float,
    # AiSession → its public projection, set/tuple → list.
def dump_json(obj: Any) -> str:   # to_jsonable + json.dumps(indent=2, sort_keys=False) + "\n"
def emit(obj: Any) -> None:       # sys.stdout.write(dump_json(obj)); used by every --json branch
```

- One recursion handles every report dataclass (`AiReport`,
  `UsageAnalytics`, budget rows, `ActiveTimer`, the evidence metrics
  dataclass). No per-command serialiser.
- `doctor`/`health`/`usage` migrate to `emit(...)`. Their **current
  top-level keys are preserved** (golden-file test pins them) so
  existing consumers don't break; only the plumbing unifies.

## Per-command output (top-level object)

- `report` → `{period_label, totals:{cost,input,output,cache_read,
  cache_write,tool_calls,tool_errors}, by_project[], by_model[],
  by_tool[], unattributed_count, attribution:{…confidence mix},
  sessions?:[…] }` (sessions list gated behind `--json-sessions` to
  keep default payloads small; default omits the per-session array).
- `budget` → `[{project, limit_usd, spend_usd, pct, state}]` (state =
  ok|warn|over) — the CI gate shape.
- `status` → `{active:bool, slug?, started?, elapsed_minutes}`.
- `evidence --json` → `{period_label, metrics:{…}, cost:{direct,
  allocated,total}, notes:[…], pr_refs:[…]}`; **no digest field** —
  documented that the v2.68 digest covers the markdown only.

## CLI contract

- `--json` ⇒ build the same report object the text path builds, then
  `jsonio.emit(...)` and return; **no** `console.print` runs (guard
  at the top of each command). Error/exit conditions identical to the
  text path (e.g. "no project" still exits 1, as JSON `{"error":…}`).
- Mutually exclusive with human formatting; `--json` always wins.

## Tests (`tests/test_v269_json_output.py`)

1. Each of report/budget/status/usage/health/evidence `--json`:
   stdout is parseable JSON, no Rich markup (`[` style tags) leaks.
2. Stable top-level keys per command (golden key-set assertion);
   datetimes are ISO strings; Paths are strings.
3. `report --json` totals equal the text path's numbers (same build,
   different projection).
4. Migration no-op: `doctor`/`health`/`usage` `--json` top-level
   keys unchanged vs pre-v2.69 (pinned).
5. Error path: no-project `report --json` exits non-zero and emits
   `{"error": …}` (still machine-parseable).
6. `evidence --json` has metrics but no `digest` key; the markdown
   path still carries the digest (cross-check).

## Docs

`docs/PRD-ai-work-ledger.md` + `README`: a "JSON output" subsection —
which commands, the additive-only stability promise, and that the
evidence digest covers markdown only. `docs/trust-model.md`: JSON
preserves trust/confidence labels (not flattened).

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry. Feature changeset (new public contract) — full spec.
