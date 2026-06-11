# v5.23 — Design

## Where the check lives

`doctor.py` gains `_ledger_duplicate_checks(project_dir, hub_dir)`, called
from `build_doctor_report` after `_collector_state_checks`. It iterates the
same `(project_dir, hub_dir)` pair as `_sessions_for`, deduplicated by
`resolve()`, so a project that *is* the hub is scanned once.

## Raw lines, not parsed sessions

The check reads raw `s` lines (`path.read_text`, `OSError`-tolerant — the
same pattern as `_count_session_lines`), **not** `parse_sessions` output:

- `parse_sessions` ends in `collapse_gemini_sessions`, which canonicalises
  exactly the rows this canary must count — the collapse layer is the reason
  doctor was blind in the first place.
- Byte-identity is a property of the line, not the parsed object.

One pass per ledger collects both signals:

1. `Counter` of stripped `s` lines → byte-identical duplicates. Surplus =
   `sum(count - 1)`; also distinct duplicated lines and the max repeat
   count (the "143x" headline number).
2. Per `job_id` (lines pre-filtered on a `" job_id="` substring, then
   parsed via `AiSession.from_log_line` for end/tokens), a count of
   *stalled* rows: a row whose end time AND `input+output` total both fail
   to exceed the group's running maxima. ≥ `_DUP_JOB_STALLED_THRESHOLD`
   (5) stalled rows fires the check.

## Stalled rows, not raw row counts

The first cut used a raw same-job_id row count (threshold 20) and was
falsified by the very first live run: the repo ledger holds a legitimate
3-day codex session (`codex:019e9da1…`) with 48 rows — one per import tick
while the rollout file grew, every row advancing in end time and token
total, all collapsing correctly at read time. That is the `id→size` growth
mechanism working as designed (v5.2), and no fixed count separates it from
a loop, because a session can live arbitrarily long.

What a loop can never do is *advance*: re-appending an unchanged session
repeats the same end/token totals (the v5.21 gemini rows were verbatim
repeats — 142 of 143 stalled). Growth re-imports score zero stalled rows by
construction. A small number of stalled rows is still legitimate — e.g. one
re-append after an import-state reset, exactly what the v5.21 repair's
state-file reset produced — so the threshold is 5, not 1.

The two signals overlap deliberately (the v5.21 rows were both byte-identical
*and* stalled): a runaway importer whose rows embed a changing timestamp or
cost defeats byte-identity but not the stall count, and a duplicate writer
with no job_id (raw external append) defeats the stall count but not
byte-identity.

## Check shape

- ids: `ledger.duplicates.<dir>` / `ledger.job_rows.<dir>` (dir string —
  unique when both project and hub ledgers report, matching the per-remote
  `attr.remote.<remote>` precedent).
- status: always `warning` (reports stay correct; exit-code contract
  preserved — same posture as drift/coverage/attribution canaries).
- detail: counts + worst offender (`"447 surplus byte-identical `s` row(s)
  (3 distinct line(s), worst x144)"` / `"gemini:<id> x142 stalled (of 143
  rows)"`, top 3 job_ids listed).
- fix: investigate-first remediation, then the v5.21 repair procedure:
  check the importer / import timer for a re-append loop; reports already
  collapse duplicates; to reclaim the file — stop the hub daemon and import
  timer, back up `ai-sessions.log`, remove duplicate lines keeping the first
  occurrence. Doctor itself never writes.

## Non-goals honoured

- Read-only: no quarantine write, no compaction, no log mutation.
- No `parse_sessions` dependency → no interaction with amendments,
  synthetic-telemetry exclusion, or alias canonicalisation; the canary sees
  the file as the bytes it is. (Individual job_id lines are parsed with
  `AiSession.from_log_line` for end/tokens — per-line, no collapse, the
  same pattern as `_group_unattributed_by_remote`.)
