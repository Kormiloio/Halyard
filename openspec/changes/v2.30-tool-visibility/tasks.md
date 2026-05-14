# v2.30 Tool Visibility — Tasks

Complete in order. Each section builds on the previous.

---

## 1. Enrich AiReport with tool usage buckets

- [x] 1.1 `src/halyard/reports.py`
  - [x] Read `_bucket_costs()` and `ToolUsageBucket` (imported from `usage.py`)
  - [x] Add a standalone `_tool_buckets_for_report(sessions: list[AiSession]) -> list[ToolUsageBucket]`:
    - Groups sessions by `session.tool` (treat `None`/empty as `"unknown"`)
    - Per group: `sessions=count`, `tokens=sum(s.input_tokens + s.output_tokens)`,
      `cost_usd=sum(s.cost_usd)`
    - Computes `session_share = count / total_sessions` (0.0 if no sessions)
    - Returns list sorted by `sessions` desc, ties by `tokens` desc, then `tool` asc
  - [x] Add `by_tool_usage: list[ToolUsageBucket]` field to `AiReport` dataclass
  - [x] In `summarize_ai_sessions()`, populate `by_tool_usage` from `_tool_buckets_for_report(sessions)`
  - [x] Keep existing `by_tool: list[CostBucket]` unchanged

- [x] 1.2 `tests/test_reports.py`
  - [x] Test: two tools, one with cost=0 — both appear in `by_tool_usage`
  - [x] Test: sort order — 2 claude-code sessions before 1 codex session
  - [x] Test: tokens sum matches `input_tokens + output_tokens` per tool
  - [x] Test: `session_share` sums to 1.0 across all tools
  - [x] Test: empty sessions → empty list

---

## 2. CLI — add "By tool" to `halyard report`

- [x] 2.1 `src/halyard/cli.py`
  - [x] After "By model", add a "By tool" section using `report.by_tool_usage`
  - [x] Row format: tool, sessions, tokens (if available), cost
  - [x] Omit the "By tool" section if `report.by_tool_usage` is empty

- [ ] 2.2 Manual smoke test
  - [ ] Run `halyard report` in the Halyard project dir
  - [ ] Confirm "By tool" section appears with all tools including zero-cost ones

---

## 3. Dashboard — tool table with session-count bars

- [x] 3.1 `src/halyard/dashboard.py`
  - [x] Add `_tool_table(buckets: list[ToolUsageBucket]) -> str`:
    - Columns: Tool · Sessions · Tokens · Cost · Share
    - Bar width = `int(bucket.session_share * 100)` — not cost%
    - Token cell uses `compact_number(bucket.tokens)`
    - Empty state: `<p class="empty">No tool data yet.</p>`
    - No row cap — show all tools
  - [x] Replace `{_bucket_table(report.by_tool, "Tool")}` with `{_tool_table(report.by_tool_usage)}`

---

## 4. Dashboard — fix usage analytics panel

- [x] 4.1 `src/halyard/dashboard.py` — `_usage_tool_rows()`
  - [x] Remove `[:4]` slice — show all tools
  - [x] Add tokens to each row label when `bucket.tokens > 0`

---

## 5. Regression suite and final checks

- [x] 5.1 Run full test suite: 918 passed, 0 failed (pre-existing test_db and test_manual_sessions excluded)
- [x] 5.2 `uv run ruff check .` — clean
- [ ] 5.3 `uv run ruff format --check .` — clean
- [ ] 5.4 `uv run mypy src` — clean
- [ ] 5.5 Manual dashboard check

---

## 6. Update docs

- [x] 6.1 `openspec/project.md` — added v2.30 entry
- [x] 6.2 `docs/current-direction.md` — added v2.30 to build sequence
