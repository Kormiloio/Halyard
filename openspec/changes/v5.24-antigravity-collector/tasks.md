# v5.24 — Tasks

## Phase 0 — format spike (DONE 2026-08-09)

- [x] Run a real conversation in Antigravity (40 min, 355 transcript
      records).
- [x] Record file layout, naming, and conversation-id source in
      `design.md` § Phase 0. Cascade id = `.db` name = `brain/` dir name.
- [x] Record encoding: `conversations/*.db` is SQLite wrapping binary
      protobuf (**rejected**); `transcript.jsonl` is clean JSONL
      (**the target**).
- [x] Record available fields: `step_index`, `source`, `type`, `status`,
      `created_at`, `content`, `tool_calls`, `exit_code`, `thinking`.
- [x] Record growth behaviour: conversations resume in place → high-water
      mark is line count / last `step_index`.
- [x] Confirm model/token availability: **none anywhere**;
      `modelName: "auto"`. `telemetry_trust` fixed to `inferred`.
- [x] Amend `design.md` — three first-draft assumptions were wrong
      (hook surface exists; protobuf is not the target; transcript path
      differs from the documented one).
- [ ] **Open:** multi-conversation and multi-workspace behaviour — only
      one conversation has been observed. Confirm `brain/` holds one
      directory per conversation and that `workspacePaths` can hold more
      than one entry.
- [x] Decide with the user whether a spend-blind collector is worth
      shipping: **ship it, quarantined from spend** (2026-08-09). See
      `design.md` § Spend quarantine.

## Spend quarantine

- [x] Emit `billing=credits`, `tokens_available=false`,
      `telemetry_trust=inferred`, zero tokens, zero cost.
- [x] Verify no change is needed in `usage.sum_spend` — the existing
      `api_only` filter should already exclude these rows on both the
      `billing != "api"` and `cost_usd <= 0` conditions. Add a test
      pinning that, rather than assuming it.
- [x] Dashboard + CLI: spend column renders `n/a` (not `$0.00`) for
      tools that report no spend, via `ToolUsageBucket.spend_tracked`.
- [ ] **Deferred:** a separate visual time-only *bucket* in the dashboard.
      The `n/a` cell satisfies the honesty requirement; grouping is cosmetic.
- [x] `report` / `usage`: render "n/a — not spend-tracked" where a spend
      column would otherwise show `$0.00`.
- [x] `doctor`: when Antigravity rows exist, state that time is captured
      but spend is not tracked.
- [x] Test: Antigravity rows excluded from budget and invoice spend.
- [x] Test: a spend-bearing tool does **not** inherit the quarantine.
- [x] Test: Antigravity time still reaches invoices and timeclock
      reconciliation — quarantine is spend-only, never time.

## Code

- [x] `src/halyard/collectors/antigravity.py` — reads only under
      `~/.gemini/antigravity/`.
- [x] Growth-aware state file `~/.halyard/antigravity-imported`
      (`{conversation_id → high-water mark}`), not a bare id set.
- [x] `job_id = antigravity:{conversation_id}`; `tool = antigravity`;
      `telemetry_source = antigravity-conversations`.
- [x] `telemetry_trust` = `observed` or `inferred` per the model-id
      finding.
- [x] Explicit exclusion of `~/.gemini/antigravity/` in
      `gemini_history.py` (`_FOREIGN_ROOTS` / `_is_foreign`).
- [x] `halyard import-antigravity` with `--dry-run` and `--all`, matching
      the existing importer contract.
- [x] Register in `import-all` so the scheduled LaunchAgent covers it.
- [x] `_antigravity_checks(...)` in `doctor.py`: skipped / uncaptured /
      lagging / current. Use real command names in `fix=` strings.

## Tests (`tests/test_v524_antigravity_collector.py`)

- [x] Golden-file: sample conversation → expected `s` row.
- [x] Idempotence: importing twice appends exactly one row.
- [x] Growth: conversation gains messages → prior row superseded, not
      duplicated (the v5.2 / v5.21 / v5.22 defect class).
- [x] Isolation: Antigravity fixtures yield zero Gemini rows.
- [x] Isolation: Gemini fixtures yield zero Antigravity rows.
- [x] Doctor: app absent → skipped.
- [x] Doctor: present but uncaptured → warning with a command that
      actually resolves.
- [x] Doctor: captured but stale conversations → lagging warning
      (`antigravity` added to `_COVERAGE_TOOLS`).
- [x] v5.23 ledger duplicate canary quiet on a mixed-tool ledger.
- [x] Any timing assertion uses the `perf_ceiling` fixture.

## Docs

- [x] Correct the "Antigravity (Gemini CLI)" conflation in
      `docs/PRD-developer-experience.md:23`; they are separate products.
- [x] Sweep the rest of that PRD for the same conflation
      (lines ~48, ~263, ~309, ~315 mention Antigravity as a design
      advisor — those are fine, but check the wording).
- [x] Add Antigravity to the supported-tool matrix in `README.md`.
- [x] Update roadmap status and test count in `openspec/project.md`.

## Gate

- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run mypy src/`
- [x] `uv run pytest` — 1792 passed. One pre-existing unrelated failure
      (`test_v252_tool_detection.py::test_absent_tool_no_nudge`) also fails
      on the base source with all `src/` changes stashed; it is non-hermetic
      and reads the real `$HOME`. Tracked separately.
      NOTE: `uv` is not installed on this machine; ran via a local `.venv`
      (Python 3.12) created with `pip install -e ".[dev]"`.
