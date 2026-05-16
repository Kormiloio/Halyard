# Spec: Machine-readable JSON output

## Requirement: One JSON convention

A shared `jsonio` seam MUST serialise report/analytics dataclasses
deterministically: `datetime`/`date` → ISO 8601 strings, `Path` →
str, `Decimal` → float, dataclass → object, set/tuple → array. Every
`--json` branch MUST route through it. `doctor`, `health`, `usage`,
`log`, `outcome` MUST be migrated onto it with their existing
top-level keys preserved.

### Scenario: existing consumers unaffected
- GIVEN a pre-v2.69 caller of `doctor --json` / `health --json` /
  `usage --json`
- THEN the top-level keys and value types are unchanged.

## Requirement: Complete read-surface coverage

`report`, `budget`, and `status` MUST gain `--json`. `evidence` MUST
gain `--json` emitting the structured appendix metrics.

### Scenario: report json
- WHEN `halyard report --json` runs on a populated ledger
- THEN stdout is a single JSON object whose totals equal the text
  path's numbers, with no Rich markup.

### Scenario: budget gate shape
- WHEN `halyard budget --json` runs
- THEN it emits a list of `{project, limit_usd, spend_usd, pct,
  state}` suitable for a CI threshold check.

### Scenario: status statusline shape
- WHEN `halyard status --json` runs
- THEN `{active, slug?, started?, elapsed_minutes}`.

## Requirement: Clean machine contract

With `--json`, stdout MUST contain only JSON — no Rich markup, no
human lines. Exit conditions MUST match the text path; an error MUST
still be machine-parseable (`{"error": "..."}` with non-zero exit).
Human output MUST be unchanged when `--json` is absent.

## Requirement: Trust labels preserved in JSON

Captured/allocated/inferred cost basis and attribution-confidence
MUST appear as fields in the JSON, not be flattened away. The machine
reader gets the same honesty as the human reader.

## Requirement: Evidence digest scope

`evidence --json` MUST NOT carry an integrity digest. The v2.68
`sha256:` digest is defined over the **markdown** artifact only; this
MUST be documented so no consumer treats the JSON as a digested
artifact.

## Requirement: Additive stability

The JSON schema is semi-stable and additive-only: new keys MAY be
added; existing key names/types MUST NOT change without an explicit
version note in the PRD. No published JSON Schema file until an
external consumer exists.
