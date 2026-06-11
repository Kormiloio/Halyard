# v5.22 — Tasks

## Code

- [x] `copilot.py`: state file → codex `id→size` format (`_load`/`_save`,
      prune missing files, legacy bare-id re-check).
- [x] `copilot.py`: `job_id=copilot:<id>` on imported rows.
- [x] `copilot.py`: `_ledger_covered_ids` (all non-`copilot:` rows)
      replaces the OTel-only coverage check.
- [x] `record_otel_capture` adapted to the dict state, semantics unchanged.
- [x] `ai_log.py`: `_copilot_session_key` (job-id prefix only) wired into
      `_redundant_session_key`.

## Tests (`tests/test_v522_copilot_growth_reimport.py`)

- [x] Grown chat session re-imports; rows collapse to the fuller one at
      read time.
- [x] Unchanged session skips (size match).
- [x] Legacy bare-id state entry re-checks once; ledger-covered session
      (pre-v5.22 import row) is skipped, never double-counted.
- [x] OTel-captured session stays skipped (state fast path and ledger
      backstop).
- [x] `copilot-otel:` rows never collapse with `copilot:` rows.

## Gates

- [x] ruff check + format, mypy clean; full pytest suite green (1758 tests).

## Docs (PRD / ARD / spec sync)

- [x] `docs/collector-coverage.md`: copilot importer collapse/growth note
      (alongside the existing gemini/codex notes).
- [x] `docs/PRD-vscode-extension-and-metadata-parity.md`: requirement that
      long-lived chat sessions stay current via the import timer.
- [x] `docs/ARD-vscode-extension-and-metadata-parity.md`: growth re-import
      + collapse mechanism.
- [x] `openspec/project.md`: roadmap entry + test count.

## Operational

- [x] Refresh session `78930975…`: backup, drop pre-fix-parser row, clear
      state entry, re-import, verify one `job_id=copilot:` row.
- [x] Verify import-all idempotence after refresh
      (`Codex 0, Copilot 0, Gemini 0, Claude 0`; state records id\tsize).
