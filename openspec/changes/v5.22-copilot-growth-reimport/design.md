# v5.22 — Design

## State format (codex v5.2 pattern, third instance)

`_load_imported_state()` returns `dict[str, int | None]`; lines are
`"<id>\t<size>"`. A session re-imports when its file size differs from the
recorded one; legacy bare ids parse to None and re-check once. On save,
ids whose chat file no longer exists are pruned (codex pattern), and
`newly_imported` sizes overwrite carried-forward entries.

`record_otel_capture(session_id)` still inserts the id with no size (the
OTel receiver cannot know the chat file's size). Its one re-check parses
the file and hits the ledger coverage check (the OTel row is there), so the
documented "survives a cleared state file" guarantee is unchanged.

## Collapse key

`_copilot_session_key` matches `tool == "github-copilot"` rows whose
`job_id` starts with `copilot:` — the same deliberately-narrow shape as
`_claude_session_key`. No `session_id` fallback: OTel-sourced rows and
pre-v5.22 import rows carry `session_id` without that job prefix and must
never collapse with anything (there is no guarantee they are cumulative
snapshots of the same accounting). `copilot-otel:<id>` does not match the
`copilot:` prefix (the character after "copilot" is `-`, not `:`), so the
two namespaces stay disjoint. `_canonical_gemini_row`'s most-complete-wins
rank keeps the latest re-import naturally.

## Coverage check

`_ledger_covered_ids(target_dir)` generalises `_otel_captured_ids`: the
session ids of every `github-copilot` row except `job_id=copilot:` rows.
This covers OTel rows (by `telemetry_source`/`copilot-otel:` job id, as
before), pre-v5.22 import rows, and manual rows — all of which would
double-count next to a fresh import row, because none of them collapse
with it. Consequence: pre-v5.22 imported sessions stay frozen at their old
snapshot unless explicitly refreshed (row + state entry removed); only the
one known-bad row (`78930975…`, written by the incident session's pre-fix
parser) is refreshed as part of this change.

The per-target cache and the "failures degrade to the state-file fast
path" behaviour are unchanged.

## Operational refresh of `78930975…`

With the timer paused implicitly by ordering (refresh runs after gates):
back up the Halyard ledger, drop the single
`session_id=78930975… telemetry_source=copilot-jsonl` row, remove the
state entry, run `halyard import-copilot`, verify exactly one new row with
`job_id=copilot:78930975…` and sane interaction counts. Future growth
(e.g. the June 10 continuation, once VS Code flushes it) re-imports on the
next timer tick and collapses at read time.
