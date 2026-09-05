# v5.32 — Tasks

## Code

- [x] `codex_app._MAX_ROLLOUT_LINE_BYTES = 16 MiB` — per-line bound, the one
      that actually matches a streaming read.
- [x] `codex_app._MAX_ROLLOUT_BYTES` 25 MB → 1 GiB — total parse budget,
      sized above real rollouts (813 MB observed) instead of an order of
      magnitude below them.
- [x] `_iter_jsonl_lines`: stream with both bounds. Over-long line → skip
      that line and continue. Over budget → stop and keep what was read.
- [x] `_note_truncated`: report truncation through `ai_log._log_error`, the
      established degraded-but-continuing channel.
- [x] Symlink rejection unchanged.

## Tests (`tests/test_v532_codex_oversized_rollout.py`)

- [x] A ~30 MB file (past the old cap) is read. **Fails without the fix.**
- [x] An over-long line is skipped, the file keeps reading. **Fails without
      the fix.**
- [x] Over budget truncates *and* reports. **Fails without the fix.**
- [x] `_note_truncated` reaches `_log_error` with the file name and offset.
      **Fails without the fix.**
- [x] Symlinks still refused (unchanged — and it still passes unfixed,
      which is the point).
- [x] The budget is sized above real rollouts. **Fails without the fix.**

## Verification against the real rollout

Measured on the 813 MB file that motivated this, before and after:

- [x] lines yielded: 0 → 13,338
- [x] `_parse_session_file`: `None` → parses
- [x] `halyard import-codex`: "No new Codex sessions" → imports 2
- [x] recorded Codex total: 148,225,877 → 419,845,235
- [x] one session: 103,842,457 → 371,138,080 (the earlier figure came from a
      19.7 MB snapshot of a now-852 MB file)
- [x] `halyard doctor` drift canary: firing → silent

## Gates

- [x] `uv run pytest` — 1845 passing (+6).
- [x] `uv run ruff check .` and `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Out of scope (recorded, not done)

- [ ] The same whole-file cap in the other collectors:
      `claude_code.py:719` (25 MB), `gemini_otel.py:25` (25 MB),
      `antigravity.py:61` (50 MB). None of them warn on skip either. Only
      Codex is demonstrably losing data here; widening to every collector's
      untrusted-input handling at once is a much larger review.
- [ ] A first-class `halyard doctor` check for truncated/skipped rollouts.
      The diagnostic-log entry makes the loss discoverable; a doctor check
      is the better end state and belongs with the cross-collector pass.
- [ ] Re-deriving spend/usage analysis from the corrected ledger. The
      numbers are now right; conclusions previously drawn from them are not.
