# Tasks: Streaming `ai-sessions.log` Parser

## Implementation

- [x] Add `_iter_log_lines(path)` helper in `ai_log.py` that yields stripped
  lines from a file opened in text mode with `encoding="utf-8"`.
- [x] Rewrite `parse_sessions()` to use `_iter_log_lines()` instead of
  `read_text().splitlines()`.
- [x] Rewrite `unattributed_log_count()` (no `_session_count_in` exists; this
  was the only sibling reader still using `read_text().splitlines()`) to
  iterate the file directly.
- [ ] DROPPED: extracting an amendment-folding helper from
  `_effective_session_lines()`. Its callers already have `content` fully in
  memory (built inside a `locked_file` block), so the streaming gain doesn't
  apply. Left untouched.

## Tests

- [x] Add a streaming-parity test: hand-build a fixture log with a mix of
  `s` lines, `a` amendments, header comments, malformed lines, and assert
  `parse_sessions()` returns the same shape as a baseline list assembled
  by hand.
- [x] Add a memory smoke test: build a synthetic 50 000-line log in
  `tmp_path`, parse it, and assert the resulting session list is well-formed.
  Memory thresholds are documented in the spec but not asserted in CI
  (too flaky).
- [x] Verify quarantine still fires for malformed lines on the streaming
  path.

## Verification

- [x] `uv run pytest tests/` — all green.
- [x] `uv run ruff check .` — clean.
- [x] `uv run mypy src/halyard/ai_log.py` — clean.
