# v5.40 — Tasks

## Code

- [x] `_canonical_gemini_row` inherits `source_path` as well as `project`
      when the winner lacks it.
- [x] `_inherited_project` generalised to `_agreed(rows, attr)`; the old
      name kept as a back-compat alias.
- [x] Explicit keyword arguments to `replace` rather than a dict splat, so
      mypy still checks the field names.
- [x] Early return preserved: when nothing is inherited the winner is
      returned unchanged, not copied.

## Tests (appended to `tests/test_v536_attribution_recovery.py`)

Placed with the v5.36 tests on purpose — this is the same rule, and a
future field should find both cases together.

- [x] The winning row inherits the group's `source_path` (107,376-token
      row carries the path; 2,019,287-token row wins and takes it).
- [x] A winner with its own path is untouched.
- [x] A group disagreeing on the path stays pathless.
- [x] Project and path are inherited independently.

## Verified against real data

- [x] Re-read the live hub: the Mycelium session (`codex:01a0435e`) now
      carries `.../ChatGPT/Mycelium`, so `halyard link-path` can reach it.
- [x] Six sessions carry a path where five did; no row lost one.

## Gates

- [x] `uv run pytest` — **1952 passing** (+4).
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/` — clean, 105 files.
