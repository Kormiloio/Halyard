# Tasks: v2.21 — Attribution Provenance

Retroactive spec for D-1: attribution provenance / attr_method log format
addition. All tasks completed by Kai. 12 new tests added.

## Spec & design
- [x] Write proposal.md
- [x] Write specs/attribution-provenance.md
- [x] Write design.md

---

## AiSession model

- [x] Add `attr_method: str | None = None` field to `AiSession`
- [x] Update `to_log_line()` to append `attr_method=<value>` when non-None
- [x] Update `_parse_line_result()` / `from_log_line()` to read `attr_method`
  from KV section; default to `None` if absent

---

## Collector wiring (all three: claude_code, cursor, gemini_cli)

- [x] Check `~/.halyard/active` first; if matching, set `attr_method="timer"`,
  do NOT add `attribution:inferred` tag
- [x] Else check for `halyard.toml` walking up from CWD; if found, set
  `attr_method="ws_root"`, add `attribution:inferred` tag
- [x] Else check git remote; if resolvable, set `attr_method="git"`, add
  `attribution:inferred` tag
- [x] Else leave `attr_method=None`; session written to unattributed log

---

## Backfill functions

- [x] `assign_unattributed_sessions()` — set `attr_method="backfill"` on
  attributed sessions
- [x] `backfill_window()` — set `attr_method="backfill"` on attributed sessions

---

## Tests (`tests/test_attr_method_serialization.py`)
- [x] `test_attr_method_timer_serialized`
- [x] `test_attr_method_ws_root_serialized`
- [x] `test_attr_method_git_serialized`
- [x] `test_attr_method_backfill_serialized`
- [x] `test_attr_method_none_omitted`
- [x] `test_attr_method_missing_parses_as_none`

## Tests (`tests/test_collector_attr_method.py`)
- [x] `test_timer_attribution_sets_timer_method`
- [x] `test_ws_root_attribution_sets_ws_root_method`
- [x] `test_git_attribution_sets_git_method`
- [x] `test_timer_takes_precedence_over_git`

## Tests (`tests/test_backfill_attr_method.py`)
- [x] `test_assign_unattributed_sets_backfill`
- [x] `test_backfill_window_sets_backfill`

## Quality
- [x] Run full test suite — all passing (12 new tests, 2026-05-08)
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
