# v5.29 — Tasks

## Code

- [x] `hub.py`: add `configured_hub_path()` returning the pointer target
      regardless of existence. `find_hub()` unchanged.
- [x] `doctor.py`: new `hub.stale` check in `_hub_checks`, ordered before
      the `hub.configured` branch. Status `error`; detail names the
      configured path, says it no longer exists, and states that sessions
      are diverting to `~/.halyard/unattributed.log` and are recoverable.
- [x] `doctor.py`: update both fix strings (`:134`, `:189`) from
      `halyard hub <path>` to `halyard hub set <path>`.
- [x] `cli_hub.py`: add `hub set <PATH>` and `hub show`.
- [x] `cli_setup.py`: delete the shadowed bare `hub` command.

## Docs

- [x] `docs/troubleshooting.md`: two occurrences of the broken
      `halyard hub /path/...` form.
- [x] `openspec/project.md`: roadmap entry + test count.

## Tests (`tests/test_v529_hub_pointer_staleness.py`)

- [x] Stale pointer (target never created) → `hub.stale`, status `error`,
      detail contains the configured path.
- [x] Stale pointer → `hub.configured` is *not* emitted (mutually
      exclusive ids).
- [x] No pointer at all → `hub.configured`, not `hub.stale` (existing
      behaviour preserved).
- [x] Valid hub → neither; `hub.valid` ok (existing behaviour preserved).
- [x] `configured_hub_path()` returns the path for a stale pointer where
      `find_hub()` returns `None`.
- [x] `configured_hub_path()` returns `None` when no pointer exists.
- [x] `find_hub()` contract unchanged: still `None` for a stale pointer.
- [x] CLI: `hub set <path>` sets the pointer; rejects a directory with no
      `halyard.toml`.
- [x] CLI: `hub show` reports the configured hub.
- [x] CLI regression: no bare `hub` command shadows the sub-app — the
      defect was invisible because both registrations succeeded.

## Gates

- [x] `uv run pytest` — 1780 passed, 11 new. One unrelated failure,
      `test_v252_tool_detection::test_absent_tool_no_nudge`: this branch
      is off `main`, which does not yet carry the v5.28 Copilot fix (PR
      #16). Goes to 1781 passing once #16 lands and this rebases.
- [x] `uv run ruff check .` and `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Out of scope (recorded, not done)

- [ ] Auto-healing a stale pointer by searching for a relocated hub.
- [ ] Relocation-proof project/hub identity (the registry
      `~/.halyard/projects` has the identical absolute-path failure mode).
