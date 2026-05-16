# Spec: Collector Schema-Drift Canary

## Requirement: Flag sustained model regression per tool

`halyard doctor` MUST emit a `warning` check `drift.<tool>` when, for
that tool, the most recent `_DRIFT_WINDOW` sessions all have an unreal
model AND at least one older session for the same tool had a real
model AND the tool has at least `_DRIFT_WINDOW` sessions total. The
check MUST carry an actionable `fix`.

### Scenario: regression after a healthy history
- GIVEN ≥5 `claude-code` sessions captured a real model, then the most
  recent 5 all have `model` unreal (empty / "default" / `*-unknown`)
- WHEN `halyard doctor` runs
- THEN the report contains `drift.claude-code`, status `warning`.

### Scenario: healthy tool → no canary
- GIVEN every recent `cursor` session has a real model
- THEN there is no `drift.cursor` check.

### Scenario: never-healthy tool → no canary
- GIVEN a tool whose sessions have *always* had an unreal model (no
  healthy baseline)
- THEN there is no `drift.<tool>` check (this is not a regression).

### Scenario: insufficient history → no canary
- GIVEN a tool with fewer than `_DRIFT_WINDOW` sessions
- THEN there is no `drift.<tool>` check.

### Scenario: non-sustained → no canary
- GIVEN the recent window contains at least one real-model session
- THEN there is no `drift.<tool>` check (only *sustained* runs fire).

## Requirement: Per-tool isolation

A drifting tool MUST NOT cause a `drift.*` check for any other tool;
each tool is evaluated against its own history independently.

## Requirement: Exit-code contract preserved

`drift.*` checks MUST be `warning`, never `error`; `has_errors(report)`
MUST stay False when the only non-ok checks are `drift.*`.

## Requirement: Read-only, on-demand

The canary MUST run only inside `build_doctor_report()` and MUST NOT
read upstream tool formats, mutate state, or start any background
process.
