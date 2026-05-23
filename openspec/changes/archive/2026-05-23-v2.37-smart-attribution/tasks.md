# v2.37 — Smart Attribution: Tasks

## Completed — 2026-05-15

- [x] **`_slug_from_halyard_toml`** — new function in `git_context.py` that walks
  CWD → root looking for `halyard.toml` with `[project].slug`. Stops at first
  `halyard.toml` found (with or without slug).
- [x] **`infer_project` updated** — calls `_slug_from_halyard_toml` first (priority 2),
  falls through to `repos.toml` and git auto-slug as before.
- [x] **Tests** — 4 new tests in `test_git_context.py`:
  - `test_infer_project_halyard_toml_in_cwd`
  - `test_infer_project_halyard_toml_in_parent`
  - `test_infer_project_halyard_toml_beats_repos`
  - `test_infer_project_halyard_toml_no_slug_falls_through`
- [x] **`halyard adopt`** — new command in `cli_setup.py`. Writes minimal
  `halyard.toml`, wires `repos.toml`, registers path. Handles no-git-remote
  case cleanly.
- [x] **`AiSession.remote`** — new optional field. Serialized as `remote=<value>`
  in log lines. Parsed in `_parse_line_result`. Backward-compatible.
- [x] **Claude Code collector** — writes `remote=` at session close.
- [x] **Cursor collector** — writes `remote=` at session close.
- [x] **Gemini CLI collector** — writes `remote=` at session close.
- [x] **`_group_unattributed_by_remote`** — new helper in `doctor.py`. Parses
  unattributed log and groups by `session.remote`.
- [x] **`halyard doctor` unattributed check** — now shows grouped-by-remote
  breakdown with per-repo session counts and `halyard adopt` as the fix.
- [x] **Dashboard Overview tab** — `usage_pane.py` shows `⚠ Unattributed` with
  grouped remote breakdown inline.
- [x] **Docs updated** — `PRD-halyard.md`, `PRD-developer-experience.md`,
  `openspec/project.md` all reflect the new priority stack, `adopt` command,
  and `remote` field. `assign-unattributed` references replaced with `adopt`.

## Test count at completion: 974 passing

## Open / future

- [ ] **`halyard reattribute <old-slug> <new-slug>`** — migrate historical hub
  sessions when a directory is adopted under a different slug than the auto-slug.
- [ ] **`halyard doctor` prompt in proof score** — when attribution < 100%,
  show per-repo adopt suggestions (v2.36 shows a generic fix prompt today).
- [ ] **`halyard init` slug prompt** — `scaffold_project` should ask for
  `[project].slug` during init so the full scaffold also benefits from walk-up
  attribution without a separate `adopt` step.
