# v5.23 — Doctor check for duplicate ledger rows

## Why

During the v5.21 incident, `ai-sessions.log` in the Halyard repo ledger
accumulated ~447 byte-identical duplicate `s` rows — one gemini session
re-appended 143 times by the 30-minute import timer (the gemini importer's
dedup read only `job_id=gemini:` rows while read-time collapse canonicalised
hook-covered sessions to the hook row, hiding the id the dedup looked for).
Throughout, `halyard doctor` reported **all OK**: read-time collapse hid the
duplicates from every report surface, so nothing observable degraded — but
the file grew without bound and the ledger silently stopped being a faithful
append-only record of real events.

The lesson is general: read-time collapse is a *display* defence, not a
*detection* one. Any importer regression of this class (codex v5.2, claude
v5.21, copilot v5.22 — three instances already) re-appends rows invisibly.
Doctor is the designated canary surface (drift v2.59, coverage canary,
attribution quality v2.65) and was blind to exactly this failure.

The v5.21 proposal explicitly listed this as a follow-up ("Out of scope: a
`doctor` check for duplicate ledger rows (worth a follow-up)"). This change
delivers it.

## What changes

- `halyard doctor` gains a **ledger duplicate canary** over each consulted
  ledger (project + hub, deduplicated by resolved path, same set as the
  other ledger-reading checks):
  - **Byte-identical duplicate `s` rows:** any `s` line appearing more than
    once verbatim is reported — total surplus rows, distinct duplicated
    lines, and the worst offender's repeat count. Genuine sessions have
    unique timestamps; a verbatim repeat is always a writer defect.
  - **Suspicious same-`job_id` row counts:** a single `job_id` with ≥ 5
    *stalled* rows — rows whose end time AND token total both fail to
    exceed the group's running maxima — is reported. Growing live
    transcripts legitimately re-import once per importer tick while the
    file grows (codex/claude/copilot `id→size` pattern) and every such row
    *advances*; a loop re-appending an unchanged session can never
    advance. (A raw row-count threshold was tried first and immediately
    false-positived on a legitimate 3-day codex session with 48 advancing
    rows — see design.md.)
- Both signals are `warning`, never `error` — reports remain correct (the
  collapse layer works), so the doctor exit-code contract is preserved.
- Detection only, with a suggested remediation in `fix`: identify and fix
  the re-appending importer/timer first, then (optionally) compact — stop
  the hub daemon / import timer, back up the log, remove duplicate lines
  keeping the first occurrence (the exact v5.21 repair procedure). Doctor
  never writes (read-only contract).

## Out of scope

- A `halyard compact-log` write command. Compaction mutates the ledger, the
  one file the project treats as append-only outside user-driven triage;
  automating it deserves its own proposal with the no-silent-writes
  diff-and-approve flow.
- Near-duplicate detection (same session, differing rows) — that is what
  read-time collapse already handles; the job_id count canary covers the
  runaway case.

## Impact

- Affected: `src/halyard/doctor.py`, new test suite
  `tests/test_v523_ledger_duplicate_doctor.py`.
- No schema, log-format, or CLI-surface change; the checks flow through the
  existing `DoctorReport`, so dashboard/TUI health surfaces inherit them.
