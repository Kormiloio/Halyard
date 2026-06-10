# v5.21 — Transcript importer hardening (Claude Code backfill + Copilot patch aggregation)

## Why

On 2026-06-10 an unsupervised agent session added two genuinely useful
capabilities directly to the working tree — a `halyard import-claude` bulk
importer for Claude Code transcripts, and incremental-patch aggregation in the
Copilot chat parser — then ran them against the live ledgers. The features are
wanted (claude-desktop misses Stop hooks; recent VS Code chat formats lost
evidence), but the implementation shipped unspecced, untested, failing every
quality gate, and with five defects that corrupted real data:

1. **Lossy project attribution.** Claude Code encodes `/`, `.`, and `-` all as
   `-` in `~/.claude/projects` folder names; decoding by string replacement is
   ambiguous. `-Users-camaj--claude-mem-observer-sessions` decoded to
   `/Users/camaj`, dumping 1,841 sessions into the home-directory ledger.
2. **Global plausibility guard gutted.** `_MAX_SESSION_SECONDS` was raised
   12h → 7 days so one suspicious multi-day import would pass, re-opening the
   frozen-payload hole for every collector.
3. **No ledger-aware dedup.** The importer deduped only against its own state
   file, so sessions already captured per-turn by the Stop hook were imported
   *again* as whole-session rows — double-counting tokens and cost (31 rows in
   the Halyard repo ledger alone).
4. **Poisoned dedup state.** ~1,856 session ids were recorded as "imported"
   in `~/.halyard/claude-imported` regardless of whether their rows were
   usable, permanently hiding those transcripts from any future (fixed) run.
5. **Copilot phantom requests.** A `range(max(len(requests), max_patch_idx))`
   loop padded missing indices with `{}` and counted each as a user turn.

The 30-minute `import-all` launchd timer (which runs this working tree via the
editable uv tool install) then amplified the damage on every tick.

## What changes

- **`import_claude_sessions` rebuilt on the codex importer pattern:**
  attribution from the `cwd` field inside each transcript (never from folder
  names); per-target ledger scan skips any session the Stop hook already
  recorded; codex-style `id → size` state allows growing live transcripts to
  re-import; imported rows carry `job_id=claude:<session_id>` and collapse at
  read time via `_redundant_session_key`, exactly like codex re-imports.
  Costing matches the hook path (cache tokens + multi-model breakdown).
- **`_MAX_SESSION_SECONDS` restored to 12h.** Multi-day transcripts are
  skipped by the importer, as everywhere else. Segmenting long-lived windows
  into active periods is future work, not a constant bump.
- **Read-time collapse extended to `claude:` job ids** — import rows only.
  Hook rows are per-turn deltas (not cumulative snapshots) and are never
  collapsed; the key function matches on the `job_id` prefix alone.
- **Copilot parser:** keep the list-growing `_apply_patch` and response-part
  aggregation (the real fixes), drop the phantom-request loop; iterate only
  reconstructed requests.
- **Ledger repair (operational, one-time):** with the hub daemon paused and
  timestamped backups taken — remove all `claude-code` + `source=import` rows
  (1,888 across three ledgers: home 1,841, hub 16, Halyard repo 31), compact
  byte-identical duplicate rows (~415 in the repo ledger from the timer
  re-importing unchanged gemini sessions every 30 minutes), and reset
  `~/.halyard/claude-imported` so the fixed importer re-evaluates from
  scratch.

- **Gemini importer dedup fixed** (pulled into scope during verification —
  it blocked re-enabling the timer): `run_gemini_import`'s dedup read only
  `job_id=gemini:` rows, but `parse_sessions` collapses each session to one
  canonical row and a hook row (better attributed) wins, exposing
  `session_id` instead. Hook-covered sessions were therefore invisible to
  the dedup, re-imported on every 30-minute tick, and re-hidden by collapse
  — the unbounded append loop behind the ~447 duplicate rows. The dedup now
  collects both id forms, mirroring `ai_log._gemini_session_key`.
- **Tracked-projects-only backfill** (owner decision): sweep mode
  (`all_projects=True`, which deliberately wins over `project_dir` —
  import-all passes both, and explicit-mode precedence would have absorbed
  every transcript on the machine into the current project's ledger)
  resolves per-transcript and requires an inferable project slug; a corpus
  dry-run showed 1,648/1,656 candidates were headless/observer noise.
  Explicit `halyard import-claude` runs import only transcripts resolving
  to that project (the copilot filter semantic, not the codex absorb-all).

## Out of scope

- Segmenting multi-day transcripts/chat windows into active-period sessions.
- A `doctor` check for duplicate ledger rows (worth a follow-up).

## Impact

- Affected: `src/halyard/collectors/{__init__,claude_code,copilot}.py`,
  `src/halyard/ai_log.py`, `src/halyard/cli_importers.py`, new test suite
  `tests/test_v521_transcript_importers.py`.
- `halyard import-claude` and `import-all` become safe to run on the timer.
- Backfilled sessions appear once, attributed by their transcript's `cwd`.
