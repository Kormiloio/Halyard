# Tasks: v3.15 — Cursor/Windsurf coverage canary

## Investigation (done)

- [x] Confirmed Cursor/Windsurf have no enumerable per-session files (SQLite
      `state.vscdb` / `~/.codeium/windsurf` stores); coarse storage mtime is the
      only non-fragile signal.
- [x] Verified the real state: Cursor storage (May 17) is older than its last
      capture (May 20) → must NOT warn (unused, not broken). Windsurf cascade
      (May 23 10:50) is a usable activity mtime.

## Implementation

- [x] Extend `doctor._newest_disk_activity` with `cursor` (state.vscdb mtimes)
      and `windsurf` (`~/.codeium/windsurf/cascade` mtimes).
- [x] Add `_COVERAGE_TOOLS_COARSE = ("cursor", "windsurf")` +
      `_COVERAGE_LAG_DAYS_COARSE = 4`; parameterise `_capture_coverage_checks` to
      probe both tiers with the right grace and best-effort wording. warning-only.

## Tests

- [x] cursor disk older than capture → no warning (real case).
- [x] cursor disk newer than capture beyond coarse grace → warning + fix.
- [x] within coarse grace → no warning.
- [x] no captured baseline → no warning.
- [x] file-precise tool still uses the 2-day grace (no regression).
- [x] ruff / mypy / full suite green (1445 tests, +6). Verified live: no false
      cursor/windsurf warning on the real machine.

## Docs

- [x] `docs/collector-coverage.md`: note cursor/windsurf monitoring is best-effort
      (mtime-based, no schema parsing).
- [x] `openspec/project.md` roadmap entry (v3.15).
- [x] CHANGELOG.
