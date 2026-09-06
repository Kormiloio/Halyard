# v5.38 — Tasks

## Code

- [x] `collectors/junie.py`: read `sessions/index.jsonl`, aggregate
      `modelUsage` from each session's `events.jsonl`.
- [x] Size-keyed growth re-import (Codex v5.2 state format), so a session
      captured mid-write is not frozen at a partial snapshot.
- [x] `billing="local"` for on-device models, keyed on model-name markers
      rather than `cost == 0.0`.
- [x] End time preferred from the last event timestamp over the index's
      `updatedAt`.
- [x] Attribution from `projectDir` via `infer_project`.
- [x] Bounded reads via the v5.34 shared `iter_bounded_lines`.
- [x] `_safe_int` degrades malformed token fields to 0 (v5.16/B08 contract).
- [x] **Not** gated on `session_is_implausible` — it dropped 2 of 4 real
      sessions. Rationale in `design.md`.

## CLI and doctor

- [x] `halyard import-junie` (`--dry-run`, `--all`).
- [x] Folded into `halyard import-all`.
- [x] `unwired.junie` doctor check: history on disk, nothing imported.
- [x] Import output names local-model sessions once, not per row.

## Tests (`tests/test_v538_junie_collector.py`)

- [x] A session is captured with its tokens; tokens sum across events.
- [x] The dominant model labels the row.
- [x] A local model is recorded but not billed.
- [x] A hosted model reporting `0.0` is **not** reclassified as local.
- [x] A hosted model keeps its cost.
- [x] A multi-day session is kept, not dropped.
- [x] A grown session re-imports; an unchanged one does not.
- [x] Dry run records no state.
- [x] Malformed index lines and token fields degrade rather than abort.
- [x] `junie_history_present` / `junie_imported_any` predicates.

## Also fixed

- [x] `test_v252_tool_detection` stubs Junie alongside Codex and Copilot.
      `junie._INDEX_FILE` is another module-level `Path.home()` constant, so
      the fixture's `Path.home` patch could not reach it and the new check
      fired off the developer's real `~/.junie` — the identical failure
      v5.28 fixed for Copilot.

## Verified against real data

- [x] 4 sessions, **23,148,120 tokens**, matching an independent raw count
      of the same files exactly.
- [x] `halyard doctor` reports `unwired.junie` before import.

## Gates

- [x] `uv run pytest` — 1931 passing.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Out of scope (recorded)

- [ ] Attribution for imported sessions whose recorded path is a parent
      directory or has since moved. All four Junie sessions and the Codex
      Mycelium session share this; it deserves one fix covering both.
