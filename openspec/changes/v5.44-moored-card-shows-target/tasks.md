# v5.44 — Tasks

## Code

- [x] Web moored card renders `N / target` in the trait slot, preserving
      an earned `creature_trait` when one exists.
- [x] CLI roster (`halyard voyage`) moored branch does the same — it had
      the identical omission, showing the count only on active rows.

## Not done, deliberately

- [x] `_DEFAULT_TARGET` stays at 20. Raising it would silently re-stage
      every existing user's projects, turning a legitimately moored
      voyage un-moored. The default is not the defect; the unexplained
      default is.
- [x] No doctor check. Moored is a *correct* state for a project past its
      target, so a warning would advise changing a setting to stop a true
      label appearing — and doctor's warning slots are for capture and
      attribution defects that cost billable minutes.

## Tests (`tests/test_v544_moored_card_target.py`, 6)

- [x] A moored card shows `107 / 20` — the case that prompted this.
- [x] An active card still shows its count (that branch was already right).
- [x] An earned trait is kept alongside the count, not replaced by it.
- [x] Raising the target to 500 un-moors the project — the knob the card
      now points at.
- [x] With no `voyages.toml` the target is 20 and 107 sessions moors it.
- [x] 21 sessions and 107 sessions read the same stage, which is why the
      count has to be visible.

## Verified against real data

- [x] `halyard voyage set kormilo:halyard --sessions 500` wrote
      `~/.halyard/hub-data/voyages.toml`; the roster moved from
      `Shipshape · Moored` to `Anchors Aweigh 108 / 500`.
- [x] Confirmed `voyage set` and the dashboard resolve the same directory
      through `find_project_dir() or find_hub()`, so the command reaches
      the panel — the feature was never broken, only unexplained.
- [x] Live panel now carries `108 / 500`, `2 / 20`, `1 / 20`.

## Gates

- [x] `uv run pytest` — **2006 passing**.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/` — clean, 105 files.

## Docs

- [ ] Roadmap entry in `openspec/project.md`.
- [ ] `CHANGELOG.md` under Unreleased.
