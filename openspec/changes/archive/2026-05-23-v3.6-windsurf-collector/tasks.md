# v3.6 — Windsurf Collector: Tasks

Status: **shipped.**

## Phase 0 — read-only spike

- [x] Author `tools/spike_windsurf_hook.py`: dumped `os.environ`,
  `sys.stdin`, and `sys.argv` to `~/.halyard/windsurf-spike.json`.
- [x] Register spike tool manually in `~/.codeium/windsurf/hooks.json`.
- [x] Run a Windsurf Cascade → recorded result (trajectory_id, model_name).
- [x] Produce a confirmed signal-table in `design.md`.

## Phase 1 — schema + implementation

- [x] Create `src/halyard/collectors/windsurf.py`.
- [x] Implement `record_turn()` and `finalize_stale_sessions()`.
- [x] Implement payload parser for model/counts from stdin.
- [x] Add `halyard install-hook-windsurf` to `cli_hooks.py`.
- [x] Add `windsurf-session-start` and `windsurf-session-stop` to `cli_hooks.py`.
- [x] Add `--windsurf` flag to `halyard setup`.
- [x] Wire `finalize_stale_sessions` into `halyard outcome sync`.

## Phase 2 — verification

- [x] `tests/test_v36_windsurf_collector.py`.
- [x] `halyard setup` integration verification.
- [x] `pytest` green.
- [x] `ruff check` + `ruff format --check` clean.
- [x] `mypy src/` clean.

## Phase 3 — docs

- [x] Update `openspec/project.md` roadmap status.
- [x] Update `docs/PRD-halyard.md` and `docs/collector-coverage.md`.
- [x] Update README "Collection" table.
