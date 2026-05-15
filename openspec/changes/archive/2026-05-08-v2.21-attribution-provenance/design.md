# v2.21 Design — Attribution Provenance

## Log format extension

A new optional KV field is appended to the space-delimited session log format:

```
s <start_iso> <end_iso> <tool> <model> <input_tokens> <output_tokens> <cost_usd> [key=value ...] [attr_method=<value>]
```

`attr_method` is the last KV field appended when present. Valid values:
`timer`, `ws_root`, `git`, `backfill`.

**Backward compatibility:** old parsers that read KV fields by key name (the
existing `from_log_line()` implementation) ignore unknown KV fields, so old
parsers reading new lines see no change. New parsers reading old lines return
`attr_method=None`.

No new dependencies. The field is a plain string.

---

## AiSession changes

`AiSession` gains one new field:

```python
attr_method: str | None = None
```

`to_log_line()` appends `attr_method=<value>` when `attr_method is not None`,
following the existing None-omission convention.

`from_log_line()` / `_parse_line_result()` reads `attr_method` from the KV
section if present; defaults to `None` if absent.

---

## Collector wiring

Each collector's `handle_agent_stop()` determines `attr_method` before
constructing `AiSession`:

1. Check `~/.halyard/active` — if set and matches, `attr_method = "timer"`.
   Do not add `attribution:inferred` tag.
2. Else check for `halyard.toml` walking up from CWD — if found,
   `attr_method = "ws_root"`. Add `attribution:inferred` tag.
3. Else check git remote — if resolvable to a known project,
   `attr_method = "git"`. Add `attribution:inferred` tag.
4. Else no attribution; `attr_method = None`. Session goes to unattributed log.

All three collectors (claude_code, cursor, gemini_cli) follow this logic.

---

## Backfill functions

`assign_unattributed_sessions()` and `backfill_window()` set
`attr_method = "backfill"` on any session they attribute. This is written via
the existing `to_log_line()` path.

---

## Test coverage

12 new tests across:
- `tests/test_attr_method_serialization.py`
  - `test_attr_method_timer_serialized`
  - `test_attr_method_ws_root_serialized`
  - `test_attr_method_git_serialized`
  - `test_attr_method_backfill_serialized`
  - `test_attr_method_none_omitted`
  - `test_attr_method_missing_parses_as_none` (old line backward compat)
- `tests/test_collector_attr_method.py`
  - `test_timer_attribution_sets_timer_method`
  - `test_ws_root_attribution_sets_ws_root_method`
  - `test_git_attribution_sets_git_method`
  - `test_timer_takes_precedence_over_git`
- `tests/test_backfill_attr_method.py`
  - `test_assign_unattributed_sets_backfill`
  - `test_backfill_window_sets_backfill`

All 12 tests pass. ruff and mypy report no new errors.
