# v5.21 — Tasks

## Containment

- [x] `launchctl bootout` the `io.kormilo.halyard.import` timer before
      touching anything (it runs the working tree every 30 minutes via the
      editable uv tool install).

## Code

- [x] Restore `_MAX_SESSION_SECONDS = 12 * 3600` in `collectors/__init__.py`.
- [x] `_TranscriptStats.cwd` + capture in `_read_from_transcript`.
- [x] Rebuild `import_claude_sessions` (codex pattern): cwd attribution,
      hook-covered skip, `id→size` state, `job_id=claude:<id>`, hook-parity
      costing, evidence/implausibility/synthetic gauntlet, dry-run.
- [x] Delete `discover_claude_projects` folder-name decoding.
- [x] `_claude_session_key` (job-id prefix only) wired into
      `_redundant_session_key`.
- [x] Copilot: drop phantom-request loop, fix B007, keep list-growing
      `_apply_patch` + response aggregation.
- [x] `cli_importers.py`: import-claude/import-all output intact, gates clean.

## Tests (`tests/test_v521_transcript_importers.py`)

- [x] Hyphen/dot-ambiguous folder name: attribution comes from transcript
      `cwd`, not the folder name (the `/Users/camaj` regression).
- [x] Session with existing hook rows in the target ledger is skipped.
- [x] Grown transcript re-imports; unchanged one is skipped (size state).
- [x] Re-imported rows collapse to one via `job_id=claude:<id>`; hook
      per-turn rows never collapse.
- [x] >12h transcript rejected (guard restored, pinned by test).
- [x] Copilot: patch beyond snapshot materialises request without phantom
      user-count inflation; response parts aggregate.
- [x] Only actually-imported ids written to state; dry-run writes nothing.

## Gates

- [x] `ruff check` + `ruff format --check` clean.
- [x] `mypy src/` clean.
- [x] Full pytest suite green (1753 tests).

## Ledger repair (one-time)

- [x] Dashboard daemon paused; all three ledgers + state file backed up
      (`*.bak-20260610T222936Z`).
- [x] Stripped `claude-code` + `source=import` rows (home 1,841 / repo 31 /
      hub 19).
- [x] Compacted byte-identical duplicate `s` rows (repo 447, home 544).
- [x] Reset `~/.halyard/claude-imported` (1,887 poisoned ids backed up).
- [x] Dashboard restarted (manually — launchd is TCC-denied on ~/Documents,
      pre-existing); import timer re-bootstrapped; fresh tick verified
      idempotent: `Codex 0, Copilot 0, Gemini 0, Claude 0`.

## Spec sync

- [x] Roadmap entry in `openspec/project.md`; test count updated.

## Pulled into scope during verification

- [x] Coverage overlap layer: legacy hook rows carry neither session_id nor
      source (430 claude-code rows in the repo ledger, only 163 with an id) —
      time-window overlap now blocks re-import; pinned by test.
- [x] Sweep/explicit mode split + slug requirement (owner decision:
      tracked projects only; 1,648/1,656 corpus candidates were headless
      noise). Sweep wins over project_dir — import-all passes both.
- [x] Gemini importer dedup reads session_id AND job_id (the 30-minute
      timer's duplicate factory — collapse canonicalised to the hook row,
      hiding the id the dedup looked for); pinned by test.
- [x] Backfill executed: 8 attributed sessions ($8.59) across minerva/hub
      and kormilo/halyard; import-all verified idempotent twice (CLI and
      launchd tick).
- [x] Superseded `openspec/changes/v5.21-pre-launch-remediation/` (agent
      -authored, framed the 7-day guard bump as a fix) removed.
