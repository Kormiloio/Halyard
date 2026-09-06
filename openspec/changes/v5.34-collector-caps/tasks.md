# v5.34 — Tasks

## Code

- [x] `collectors.iter_bounded_lines`: symlink refusal, 16 MiB per-line cap,
      1 GiB total budget, truncation reported via `_note_truncated`.
- [x] `copilot.py`: drop the 50 MB whole-file cap, stream through the shared
      reader.
- [x] `claude_code.py`: drop the size rejection from `_safe_transcript_path`
      (symlink refusal and root containment stay), stream through the reader.
- [x] `antigravity.py`: same.
- [x] `codex_app.py`: v5.32's local implementation becomes a delegation, so
      there is one reader rather than two.
- [x] `gemini_otel.py`: remove the size *rejection* only — its `fh.read`
      bound is real — and report when the read truncates.

## Tests

- [x] `tests/test_v534_collector_caps.py`: a ~30 MB file reads; an over-long
      line is skipped without killing the file; over-budget keeps what it
      read; truncation is reported; symlinks refused; missing file yields
      nothing; the budget is sized above real transcripts.
- [x] Parametrised across all four collectors: none contains `st_size >`;
      each references `iter_bounded_lines`.
- [x] `test_v239_input_injection.py` updated — the oversize rejection moved
      out of the path guard, so the test now asserts the bound where it
      lives. Symlink refusal and allowlist containment assertions unchanged.
- [x] `test_v532_codex_oversized_rollout.py` repointed at the shared reader.

## Verified against real data

- [x] The 135.9 MB Copilot chat: 0 lines → 47.
- [x] `import-copilot --all --dry-run`: 2 sessions → **3**.

## Gates

- [x] `uv run pytest` — 1897 passing.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Out of scope (recorded)

- [ ] A first-class doctor check for truncated/skipped transcripts, covering
      all collectors uniformly. v5.32 deferred it and so does this; the
      diagnostic-log entry makes the loss discoverable in the meantime.
- [ ] Re-importing the recovered Copilot history — a user action on their
      own data.
- [ ] Attribution for imported sessions, which land `(unattributed)` because
      rollouts carry no git remote.
