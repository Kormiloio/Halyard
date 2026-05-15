# Tasks: Halyard State Integrity (Phase 1)

## Implementation

- [x] Create `src/halyard/state_integrity.py` with:
  - `IntegrityMode = Literal["off", "hash"]` (phase 2 will add `"hmac"`)
  - `IntegrityError` exception subclass.
  - `current_mode() -> IntegrityMode` — read from `halyard.toml` if a
    project dir is resolvable, else `"off"`. Caches the result for the
    process lifetime; cheap on hot paths.
  - `read_trusted_state(path: Path) -> str | None` — returns file
    contents or `None` if the file is missing; raises `IntegrityError`
    on hash mismatch.
  - `write_trusted_state(path: Path, content: str) -> None` — writes
    file + sidecar atomically (uses `locked_file`).
- [x] Update `read_active_project()` in `ai_log.py` to use
  `read_trusted_state()`. Preserve the partial-write-tolerant behaviour:
  if `IntegrityError` is raised, log and return `None` rather than crash.
- [x] Update `find_hub()` in `hub.py` similarly.
- [x] Update `set_hub()` and `clear_hub()` (and any other writers of
  `~/.halyard/active` / `~/.halyard/hub`) to use `write_trusted_state()`.
- [x] Add an `Integrity` row to `halyard doctor`.

## Tests

- [x] `mode == "off"` is the default; no sidecar files are created.
- [x] `mode == "hash"`: `write_trusted_state()` creates a `.sha256` sidecar
  whose content matches `sha256(file content)`.
- [x] `mode == "hash"`: a tampered file raises `IntegrityError`.
- [x] `mode == "hash"`: a missing sidecar raises `IntegrityError`.
- [x] `mode == "hash"`: a missing target file returns `None` (not raise).
- [x] `read_active_project()` returns `None` on `IntegrityError` (does
  not crash the dashboard / hooks).
- [x] `find_hub()` returns `None` on `IntegrityError`.
- [x] Doctor row reflects the mode and verification status.

## Verification

- [x] `uv run pytest tests/` — all green.
- [x] `uv run ruff check .` — clean.
- [x] `uv run mypy src/halyard/` — clean.
