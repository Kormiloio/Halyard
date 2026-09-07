# v5.42 — Tasks

## The resolver

- [x] `fetch_prs_for_branch` passes `--state all`. `gh pr list` defaults
      to open, so a merged PR — the one outcome the panel exists to
      report — was invisible.
- [x] Cache key versioned to `{remote}:{branch}:v2`, so entries holding
      open-only results under the 1-hour TTL cannot mask the fix.

## The denominator

- [x] `LeverageSummary.resolved` (`total - unsynced`) and `.measured`
      (`resolved > 0`), both derived rather than stored.
- [x] `pct` divides by `resolved`, not `total`.
- [x] Row counts still describe the whole window — how much is unresolved
      is itself worth showing.

## Surfaces

- [x] Web panel: an unmeasured window renders `—` and says no outcome has
      been resolved, explicitly "not a score of zero".
- [x] Web panel takes **no** colour band when unmeasured — a new
      `leverage-unmeasured` class, deliberately not one of the score bands.
- [x] TUI `LeveragePane` given the same treatment. Found by the v2.70
      parity test, which is exactly what it exists for.

## Tests (`tests/test_v542_did_it_ship.py`, 8)

- [x] The gh command carries `--state all`.
- [x] It is not narrowed to `merged`, which would empty Open/Closed.
- [x] Unresolved sessions are out of the denominator (1 of 2 = 50%).
- [x] A wholly unresolved window is `measured is False`.
- [x] A genuinely zero result still reports 0% — the honest zero survives.
- [x] An empty window is not measured.
- [x] Row counts still total the window.

## Adjusted existing tests

- [x] `test_leverage_pane_shows_shipped_pct_and_buckets` asserted
      `Shipped 50%` (2 of 4) — counting an unsynced session against the
      share, which is the defect. Now 66% (2 of 3 resolved).
- [x] `test_leverage_parity_pane_matches_web_panel` follows `resolved`.

## Verified against real data

- [x] `gh pr list --head fix/v5.40-inherit-source-path` returns `[]`;
      with `--state all` it returns PR #38, MERGED.
- [x] Dry run before: **92 of 92 → none**. After: **53 merged, 39 none**.
- [x] Live sync run with `--force` to correct the 85 stale `none` records
      the open-only resolver had written.
- [x] Panel reads **57% (53 of 92 resolved)** where it read `0% of 140`.

## Gates

- [x] `uv run pytest` — **1990 passing**.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/` — clean, 105 files.

## Docs

- [ ] Roadmap entry in `openspec/project.md`.
- [ ] `CHANGELOG.md` under Unreleased.
