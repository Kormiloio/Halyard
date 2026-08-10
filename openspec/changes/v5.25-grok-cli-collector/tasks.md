# v5.25 — Tasks

## P0 — contamination (ship first, independent of the collector)

- [ ] Confirm empirically what a Grok-originated hook invocation does to
      `halyard cc-hook` and the Cursor hook commands today: no-op, error,
      or wrong-tool row. Record the answer in `design.md`.
- [ ] Identify the discriminator that proves a payload came from its own
      harness (env var, payload key, or absent `transcript_path`).
- [ ] Harden `claude_code.py` and `cursor.py` to refuse foreign payloads
      — fail-open, but never write a wrong-tool row.
- [ ] `_grok_compat_check(...)` in `doctor.py`: Grok present + Halyard
      hooks in `~/.claude/settings.json` or `~/.cursor/hooks.json` +
      compat not disabled → warning, fix = the `[compat.*] hooks = false`
      TOML snippet.
- [ ] Document the remedy in `README.md` / troubleshooting. Do **not**
      write `~/.grok/config.toml` on the user's behalf.
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
- [ ] **Open decision (blocks coding):** how to record a total-only token
      count. Either carry it in the `extra` passthrough
      (`grok_total_tokens=`) with `input_tokens`/`output_tokens` at 0 and
      `tokens_available=false`, or add a first-class `total_tokens` field
      to `AiSession`. Do not fabricate an input/output split.
- [ ] Capture a real hook payload for `SessionStart` / `Stop` /
      `StopFailure` — confirm session id, cwd, model, tokens.
- [ ] Confirm `/resume` grows a session in place and `--fork-session`
      creates a new id with a parent reference.

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
