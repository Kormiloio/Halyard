# Tasks: v2.7 — AI Work Health

## Spec and design

- [x] Write proposal.md
- [x] Write design.md
- [x] Write specs/work-health.md

## `src/halyard/work_health.py`

### Data model
- [x] Define `HealthSignal` dataclass (category, label, sessions, detail, available)
- [x] Define `WorkHealthReport` dataclass (period, session_count, signals)

### Signal detectors
- [x] `detect_high_error_rate(sessions)` — error_rate > 0.25 with tool_calls >= 5
- [x] `detect_wall_vs_active(sessions)` — active < 30% of wall time
- [x] `detect_high_spend_low_delta(sessions)` — cost >= $0.50, < 5 lines/dollar
- [x] `detect_repeated_attempts(sessions)` — 3+ sessions same project+branch+day
- [x] `detect_unattributed_high_cost(sessions)` — unattributed + cost >= p75

### Report assembly
- [x] `build_health_report(sessions, period) -> WorkHealthReport`
- [x] Handle `available=False` for each signal when required fields are absent

## `src/halyard/cli.py` — `halyard health` command

- [x] Add `health` command with `--period`, `--project`, `--format` options
- [x] Resolve project_dir via `find_project_dir() or find_hub()`
- [x] Parse sessions, apply period filter, apply project filter if given
- [x] Call `build_health_report()` and render

## Rendering

- [x] Text renderer: title, header disclaimer, per-signal rows, footer count
- [x] Text renderer: "No data — requires X" for unavailable signals
- [x] Text renderer: "0 sessions flagged" for available signals with no flags
- [x] JSON renderer: emit `WorkHealthReport` as documented schema

## Tests (`tests/test_work_health.py`)

- [x] `test_high_error_rate_fires_above_threshold`
- [x] `test_high_error_rate_ignores_small_sessions` (tool_calls < 5)
- [x] `test_high_error_rate_no_data_when_no_tool_calls`
- [x] `test_wall_vs_active_fires_below_ratio`
- [x] `test_wall_vs_active_no_data_when_fields_absent`
- [x] `test_high_spend_low_delta_fires`
- [x] `test_high_spend_low_delta_no_data_when_code_absent`
- [x] `test_repeated_attempts_fires_at_threshold`
- [x] `test_repeated_attempts_no_flag_below_threshold`
- [x] `test_unattributed_high_cost_fires_above_p75`
- [x] `test_unattributed_no_flag_when_all_attributed`
- [x] `test_build_health_report_all_signals_present`
- [x] `test_health_cli_text_output` (monkeypatched sessions)
- [x] `test_health_cli_json_output` (monkeypatched sessions)
- [x] `test_health_cli_exits_1_no_project`

## Quality

- [x] Run full test suite — all passing
- [x] Run ruff — no new errors
- [x] Run mypy — no new errors
