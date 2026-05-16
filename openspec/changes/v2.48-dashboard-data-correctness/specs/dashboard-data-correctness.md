# Spec — Dashboard data correctness

## Requirement: Aggregate-by-default dashboard

WHEN `halyard dashboard` runs without `--project-dir`
THEN the dashboard MUST present the de-duplicated union of sessions
from every registered project that still exists and has an
`ai-sessions.log`, plus the hub, computed via `build_ai_report` over
that union
AND the header MUST indicate the aggregate scope and project count
AND WHEN `--project-dir` is given the dashboard MUST scope to exactly
that project (unchanged behavior).

## Requirement: build_ai_report accepts an explicit session list

WHEN `build_ai_report` is called with `sessions=<list>`
THEN it MUST compute the report from that list and MUST NOT read the
project directory's log
AND WHEN `sessions` is omitted it MUST behave exactly as before
(parse the directory).

## Requirement: Implausible hook sessions are rejected

WHEN a Gemini/Cursor/Claude-Code stop hook would record a session
whose `end - start` exceeds 12 hours
THEN it MUST NOT be written (state still reset), in addition to the
existing evidence-free guard. "Implausible" also covers a negative
duration (end before start) — physically impossible for one turn.

## Requirement: The test suite never mutates the real registry

WHEN any test runs
THEN `registry.REGISTRY_PATH` MUST resolve to a per-test temporary
location; no test may read or write `~/.halyard/projects`.

## Requirement: Temp paths are not registrable

WHEN `register_project` is called with a path under the system
temporary directory
THEN it MUST be ignored (a real project is never under tempdir).

## Requirement: Source logs are clean behind the view

The hub and project logs MUST contain only sessions that pass
`session_has_evidence` and the implausibility guard; removed lines are
preserved in a timestamped backup + removed-file (reversible).
