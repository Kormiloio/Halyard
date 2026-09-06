# v5.39 — Tasks

## Code

- [x] `AiSession.source_path` + `FieldSpec(..., FREE_TEXT)` so a path with
      spaces round-trips percent-encoded.
- [x] Codex and Junie importers populate it even when attribution fails.
- [x] `git_context`: `_PATHS_CONFIG`, `load_paths_config`,
      `register_path`, `project_for_path` (exact match only).
- [x] `_read_toml_map` shared by the remote map and the path map, so the
      two cannot drift in how they handle a corrupt file.
- [x] `ai_log.resolve_paths`, applied in `parse_sessions` *before* the
      v5.36 collapse; fills only a missing project; cheap exit when no
      unattributed row carries a path.
- [x] `halyard link-path <path> <slug>` — dry-run by default, reports how
      many sessions would resolve.
- [x] Codex importer selects the **most frequent** `cwd`, ties breaking
      toward the first seen.

## Test isolation

- [x] `_isolate_path_map` in conftest. `_PATHS_CONFIG` is another
      module-level `Path.home()` constant and `resolve_paths` is on the
      universal read path, so without it every test consults the real map —
      one test failed order-dependently before this was added.

## Tests (`tests/test_v539_path_attribution.py`)

- [x] `source_path` round-trips percent-encoded; absent when unset.
- [x] Register and resolve a path; unmapped resolves to nothing.
- [x] Matching is exact, not prefix.
- [x] A corrupt map disables the rung rather than crashing.
- [x] A mapped path attributes history, tagged `attr_method="path-map"`.
- [x] An existing project is never overwritten.
- [x] Rows without a path, and an empty map, are cheap no-ops.
- [x] CLI: dry run writes nothing; `--apply` writes the mapping; the
      ledger is byte-identical afterwards.
- [x] Most-frequent cwd wins; ties break to first-seen; junk ignored.

## Verified against real data

- [x] Codex importer now reports the 347× path, not the 83× one it had
      been reporting — and which had been stated to the user as fact.
- [x] Junie import records `source_path` for all four sessions.
- [x] `halyard link-path` dry-run reports correctly.

## Gates

- [x] `uv run pytest` — **1948 passing**.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Known limitation (documented, not worked around)

- [ ] Rows imported before this change carry no `source_path`, so a mapping
      cannot reach them. Codex and Junie re-import as their files grow, so
      active sessions gain it; a session that has stopped growing will not.
      Forcing a re-import means editing importer state, and a command that
      silently rewrites capture state to fix attribution is a worse trade
      than a documented gap.

## Out of scope (recorded)

- [ ] Automatic path inference (basename matching, parent search). Every
      version guesses, and this track has consistently preferred a visible
      gap to a silent wrong answer.
- [ ] A doctor check listing unattributed sessions with their recorded
      paths — worth having once `source_path` is populated widely.
