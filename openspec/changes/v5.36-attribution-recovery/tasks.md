# v5.36 — Tasks

## Code

- [x] `_canonical_gemini_row` inherits the group's project when the winning
      row has none; the rank tuple is unchanged.
- [x] `_inherited_project`: returns a project only when the group agrees;
      a contradiction stays unattributed.
- [x] `halyard reattribute <source> <canonical>` — read-time alias via
      `set_project_alias`, dry-run by default, reports affected sessions.
- [x] `link-repo` now points at it, as `adopt` already did.

## Tests (`tests/test_v536_attribution_recovery.py`)

- [x] The winning row inherits the group project — the observed
      74-of-75 case, with real token values. **Fails without the fix.**
- [x] A winner with its own project is untouched.
- [x] A disagreeing group stays unattributed.
- [x] A group with no project anywhere stays unattributed.
- [x] A single row is returned unchanged; unrelated jobs are not merged.
- [x] `reattribute` resolves as a command — the guard against the phantom.
- [x] Dry run writes nothing; `--apply` records the alias; the ledger is
      byte-identical afterwards; aliasing a slug to itself is refused.

## Verified against real data

- [x] unattributed: 453.6M → **82.5M** tokens (371.1M recovered to
      `git/Nautilus`).
- [x] `reattribute git/Halyard kormilo:halyard` reports 25 sessions.
- [x] Not applied to the maintainer's alias map — their call.

## Gates

- [x] `uv run pytest` — 1918 passing.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Out of scope (recorded)

- [ ] Attributing imported sessions that carry no project at all — the
      remaining 82.5M, mostly Codex and Copilot rollouts imported without
      git context. Inferring from timing overlap or a recorded cwd is a
      feature with real false-positive risk.
