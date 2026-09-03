# v5.28 — Tasks

## Code

- [x] No production changes. (`collectors/copilot.py` and `doctor.py` are
      correct as written; both couplings are in the tests.)

## Tests — axis 1, day arithmetic (`tests/test_usage_dashboard_controls.py`)

- [x] `_seed_sessions` subtracts `timedelta(days=day_offset)` instead of
      decrementing the day field.
- [x] `microsecond=0` added to the truncation, matching the
      `strftime('%Y-%m-%dT%H:%M:%S')` serialisation.
- [x] Failure window confirmed as the 1st and 2nd only (`now.day < 3`),
      by forcing the date rather than waiting for it — the live window
      closed at 2026-09-03 mid-review.

## Tests — axis 2, real `$HOME` (`tests/test_v252_tool_detection.py`)

- [x] Import `copilot` alongside the existing `codex_app` import.
- [x] Stub `copilot_history_present` / `copilot_imported_any` to `False`
      in the autouse `_fake_home` fixture, next to the Codex stubs.
- [x] Full suite green on a machine with real VS Code Copilot
      `chatSessions` on disk and no `~/.halyard/copilot-imported`.

## Gates

- [x] `uv run pytest` — 1770 passing, 0 failing.
- [x] `uv run ruff check .` and `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Deferred (not this change)

- [ ] Suite-wide guard against module-level `Path.home()` constants
      leaking the developer's real home into tests. ~20 further sites.
      See "Out of scope" in `proposal.md`.
- [ ] `vscode-extension` CI job: 2 high-severity npm advisories under
      `node_modules/postcss`. Independent of this change.
