# v2.69 — Machine-readable JSON output

## Problem

Halyard is a *data* ledger launching to a developer/CI/agent
audience, but its reporting commands are Rich-console text only.
Audit found `--json` already exists — **inconsistently**:

- `doctor` → `doctor.render_json()` returns a **str**
- `health` → `work_health.render_json()` returns a **dict**
- `usage` → inline `dataclasses.asdict` in `cli_report.py`
- `log`, `outcome` → their own ad-hoc flags

…and the flagship **`report`**, plus **`budget`** and **`status`**,
have no `--json` at all. So the surface a scripter/CI gate would
reach for first (`report --json`, `budget --json` for spend gates,
`status --json` for statuslines) is missing, and the three existing
shapes can't be consumed uniformly.

This is a consistency + gap-fill + contract change, not a greenfield
feature.

## Goal

One JSON convention, complete coverage of the read/report commands, a
documented stability contract.

- **Single seam:** a shared `jsonio.dump_json(obj)` that serialises
  the command's primary dataclass deterministically (datetime → ISO,
  `Path` → str, `Decimal`/float stable), used by every `--json`.
  The three existing ad-hoc paths are migrated onto it (output stays
  equivalent; key names preserved where already public).
- **Coverage:** add `--json` to `report`, `budget`, `status`. Keep
  the existing `doctor`/`health`/`usage`/`log`/`outcome` working,
  routed through the shared seam.
- **`evidence --json`:** emit the structured appendix metrics (not
  the markdown). Explicitly documented: the v2.68 integrity digest is
  defined over the **markdown** artifact only; the JSON form is
  unsigned data, not a digested artifact.
- **Contract:** `--json` writes *only* JSON to stdout (no Rich
  markup, no human lines), exits non-zero on the same conditions as
  the text path, and is additive — documented as a semi-stable,
  additive-only schema (new keys may appear; existing keys/types do
  not change without a version note).

## Constraints honored

- **Additive, non-breaking.** Human output is unchanged when `--json`
  is absent. `--json` suppresses all console rendering for that run.
- **Files are the source of truth.** Pure read; JSON is a projection,
  never a new stored format.
- **Trust labels preserved.** Captured/allocated/inferred and
  attribution-confidence fields are represented in JSON, not flattened
  away — the machine reader gets the same honesty as the human one.
- **No new data.** Serialises existing report/analytics dataclasses.

## Non-goals

- Changing or "prettifying" human text output.
- A query language or filtering beyond the flags each command
  already has.
- Signing/streaming JSON; a published JSON Schema file (the contract
  is documented prose for now — a schema file waits until an external
  consumer exists, same discipline as the `ai-sessions.log` spec).

## Out of scope

`--json` for mutating/setup commands beyond what already exists
(`setup --json` stays as-is); this change is the read/report surface.
