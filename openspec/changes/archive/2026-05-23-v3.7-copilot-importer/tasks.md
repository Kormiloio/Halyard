# v3.7 — GitHub Copilot Importer: Tasks

Status: **shipped.**

## Phase 0 — read-only spike

- [x] Identified VS Code `workspaceStorage` as the primary data source.
- [x] Confirmed `chatSessions/*.jsonl` contains turn-level metadata
  (`completionTokens`, `timestamp`, `toolRequests`).
- [x] Confirmed `chatEditingSessions/*/state.json` contains the list of
  touched files.
- [x] Confirmed `workspace.json` provides the absolute project path for
  attribution.

## Phase 1 — Implementation

- [x] Create `src/halyard/collectors/copilot.py`.
- [x] Implement `discover_workspaces()` walk and path mapping.
- [x] Implement `parse_chat_session()` for JSONL turn metadata.
- [x] Implement `parse_editing_session()` for file counts.
- [x] Add `halyard import-copilot` to `cli_session.py`.
- [x] Implement idempotency tracking in `~/.halyard/copilot-imported`.
- [x] Wire `import_copilot_sessions` into `halyard outcome sync`.

## Phase 2 — Testing

- [x] Create `tests/test_v37_copilot_importer.py`.
- [x] Mocked VS Code storage directory → verify full import flow.
- [x] Privacy regression: ensure `content` strings are never logged.
- [x] Project attribution test: map multiple workspace IDs to slugs.
- [x] `pytest` green.
- [x] `ruff check` + `ruff format --check` clean.
- [x] `mypy src/` clean.

## Phase 3 — Docs

- [x] Update `openspec/project.md` roadmap status.
- [x] Update `docs/PRD-halyard.md` and `docs/collector-coverage.md`.
- [x] README "Collection" table: move Copilot to "Automated".
