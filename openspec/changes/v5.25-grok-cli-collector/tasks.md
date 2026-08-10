# v5.25 — Tasks

## P0 — contamination (ship first, independent of the collector)

> Shipped 2026-08-10. 17 tests in `tests/test_v525_grok_contamination.py`.

- [x] Confirm what a Grok-originated hook invocation does today. Grok's
      payload is camelCase (`hookEventName`, `workspaceRoot`,
      `permissionMode`); `claude_code.py` already read
      `session_id or sessionId`, so a Grok payload was picked up rather
      than rejected — a wrong-tool row, not a safe no-op.
- [x] Discriminator: the camelCase common fields Grok documents and
      neither Claude Code nor Cursor emits. A *positive* signature, not a
      heuristic on absence.
- [x] `collectors.foreign_harness()` shared guard; wired into
      `claude_code.handle_stop_hook` and `cursor.handle_stop_hook`.
      Fail-open (exit 0), clears session state, writes nothing.
- [x] `_grok_compat_check()` in `doctor.py`. Per-vendor: warns only for
      the cells still at their default, and never re-suggests a toggle
      already set. Tolerates a malformed `config.toml`.
- [x] Documented in `README.md` § Troubleshooting.
- [ ] Investigate the `sessions` compat cell — `on (default)` for cursor,
      claude, **and** codex, i.e. a second borrowing vector against three
      tools Halyard already collects from. Vendor docs say these cells
      stay "staged and inert until a foreign-session scanner consumes
      them" and need a matching `resume-*` skill, so it is not active
      today. Determine whether a Grok-side foreign-session scanner can
      produce rows Halyard would then double-count, and whether `doctor`'s
      contamination check should cover `sessions` as well as `hooks`.
      Verify with `grok inspect` (Harness Compatibility section).

## Phase 0 — session spike (DONE 2026-08-10)

- [x] Run a real Grok session so `~/.grok/sessions/` exists.
- [x] Record actual field names and types in `design.md`. **`signals.json`
      does not exist** despite the vendor docs — `summary.json` is the
      primary source and `updates.jsonl` holds the only token counter.
- [x] Confirm token availability: only `params._meta.totalTokens` in
      `updates.jsonl`, cumulative and monotonic, with **no input/output
      split and no cache breakdown**.
- [x] Confirm model id format: real (`current_model_id: "grok-4.5"`), not
      a placeholder — but **absent from `pricing.py`**.
- [x] Verify group naming: URL-encoded cwd, as documented. **`info.cwd` in
      `summary.json` is authoritative**, so group-name decoding and the
      255-byte hashed-slug `.cwd` fallback are no longer on the critical
      path.
- [x] Note the free outcome metadata: `git_remotes`, `head_branch`,
      `head_commit`, `git_root_dir`.
- [x] Decide how to record a total-only token count: **a first-class
      `total_tokens` field on `AiSession`** (2026-08-10). The `extra`
      passthrough is ruled out by the v2.75 contract — "OSS writes nothing
      into `extra`" and it is "never interpreted, scored, or trusted by
      OSS surfaces". See `design.md` § 5.
- [ ] Capture a real hook payload for `SessionStart` / `Stop` /
      `StopFailure` — confirm session id, cwd, model, tokens.
- [ ] Confirm `/resume` grows a session in place and `--fork-session`
      creates a new id with a parent reference.

## Wire format — `total_tokens` (v2.75-compliant extension)

- [ ] `FieldSpec("total_tokens", "total_tokens", FieldKind.INT)` +
      `total_tokens: int | None` on `AiSession`.
- [ ] Row in the `Optional fields` table in `cli_spec.py` — the published
      spec surface must not drift from the registry.
- [ ] Confirm the field does not disturb the content-addressed session id
      / hash used as the amendment join key.
- [ ] Backward compat: an older parser ignores the token; a newer parser
      round-trips a row that lacks it.
- [ ] Do **not** reuse `tokens_available` — it implies a meaningful
      input/output split, and `_tool_buckets_for_report` sums
      `input + output + cache` when set, so a total-only row would
      contribute 0 while claiming tokens are available. Give
      `total_tokens` its own presence semantics and teach the report
      bucket to prefer it when the split is absent.
- [ ] Test: total-only row renders real tokens in `report` / dashboard,
      not 0.
- [ ] Test: a split-bearing row is unaffected by the new path.

## Code

- [ ] `src/halyard/collectors/grok_cli.py`; reads `summary.json` in full
      and `updates.jsonl` **only** for `params._meta.totalTokens`.
- [ ] Never read `chat_history.jsonl`, and never `params.update` inside
      `updates.jsonl` (that is where content lives) — assert in a test.
- [ ] Growth-aware `~/.halyard/grok-imported`
      (`{session_id → high-water mark}`), not a bare id set.
- [ ] `tool = grok`; `job_id = grok:{session_id}`; `telemetry_source`
      `grok-signals` (hooks) / `grok-sessions` (importer).
- [ ] Hidden commands `grok-session`, `grok-hook`, `grok-fail`.
- [ ] `halyard install-hook-grok` → `~/.grok/hooks/halyard.json`
      (SessionStart, UserPromptSubmit, Stop, StopFailure).
- [ ] `halyard import-grok` with `--dry-run` and `--all`.
- [ ] Register in `import-all`.
- [ ] Honour `GROK_HOME` everywhere; no hardcoded `~/.grok`.
- [ ] Project resolution from `summary.json` `info.cwd`; group-name
      URL-decode only as a fallback.
- [ ] Doctor rows: absent / unhooked / lagging / current, real command
      names in every `fix=`.
- [ ] Add `grok-4.5` (and siblings) to `pricing.py` — currently only
      `grok-3` and `grok-3-mini`, so the observed model is unpriced.
      Note pricing alone does not enable cost: without an input/output
      split there is nothing to price.

## Tests (`tests/test_v525_grok_cli_collector.py`)

- [ ] Golden-file: `summary.json` + `updates.jsonl` → expected `s` row.
- [ ] Token total is the cumulative max from `_meta`, not a sum.
- [ ] Idempotence: importing twice appends exactly one row.
- [ ] Growth: resumed session → prior row superseded, not duplicated.
- [ ] Fork: `--fork-session` child → distinct row; parent untouched.
- [ ] Hook and importer covering the same session → one row, not two.
- [ ] Contamination: Grok-shaped payload → `cc-hook` and Cursor commands
      write no row.
- [ ] Attribution: Claude Code + Cursor + Grok fixtures → three rows,
      three tools, zero duplicates.
- [ ] Content safety: `chat_history.jsonl` never opened; `params.update`
      never read.
- [ ] Long cwd → hashed-slug group still resolves via `info.cwd`.
- [ ] `GROK_HOME` override respected.
- [ ] Doctor: absent / unhooked / contaminated / lagging / current.
- [ ] v5.23 ledger duplicate canary quiet on a mixed-tool ledger.
- [ ] Any timing assertion uses the `perf_ceiling` fixture.

## Docs

- [ ] Add Grok CLI to the supported-tool matrix in `README.md`.
- [ ] Document the compat-contamination hazard and remedy.
- [ ] Update roadmap status and test count in `openspec/project.md`.

## Gate

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy src/`
- [ ] `uv run pytest`
