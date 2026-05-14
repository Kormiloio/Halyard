# v2.29 Pre-Ship Hardening — Tasks

Priority order matches proposal. Complete in order — earlier tasks unblock later tests.

---

## 1. Windows / platform safety  ← fcntl crash

- [x] 1.1 `src/halyard/ai_log.py`
  - [x] Replace bare `import fcntl` with a conditional import:
    ```python
    import sys
    if sys.platform != "win32":
        import fcntl
    else:
        fcntl = None  # type: ignore[assignment]
    ```
  - [x] Update `locked_file()` context manager: when `fcntl is None`, skip
    `flock` calls entirely and yield the file object unchanged (no-op lock)
  - [x] Emit a one-time `sys.stderr` warning on Windows: "File locking not
    available on Windows — concurrent writes are unsafe"

- [x] 1.2 `pyproject.toml`
  - [x] Add classifiers: `"Operating System :: MacOS"`,
    `"Operating System :: POSIX"`, `"Operating System :: POSIX :: Linux"`

- [x] 1.3 `README.md`
  - [x] Add platform note under the install section:
    > **Platform:** macOS and Linux. Windows is not yet supported (requires
    > POSIX `fcntl` for safe concurrent writes). WSL2 works.

- [x] 1.4 `src/halyard/cli.py` — `doctor` command
  - [x] Add a platform check: if `sys.platform == "win32"`, output a
    `[WARN] Platform not supported` line with WSL2 suggestion

- [x] 1.5 `tests/test_platform.py` (new file)
  - [x] Mock `sys.platform = "win32"` and confirm `locked_file()` returns a
    no-op context manager without raising
  - [x] Confirm the stderr warning fires exactly once per process

---

## 2. TOML injection — voyages.py and git_context.py

- [x] 2.1 `src/halyard/voyages.py`
  - [x] Read the current `write_voyages()` f-string TOML builder
  - [x] Replace with a dict structure and a single `tomli_w.dumps()` call
  - [x] Ensure the TOML schema (array of tables `[[voyage]]`) is reproduced
    correctly — `tomli_w` uses `[{"key": val}, ...]` for array-of-tables
  - [x] Confirm `read_voyages()` can parse the `tomli_w`-generated output
    (round-trip test)

- [x] 2.2 `src/halyard/git_context.py`
  - [x] Read `_write_repos_config()` f-string TOML builder (line ~174–179)
  - [x] Replace with `tomli_w.dumps()` — the structure is a flat dict of
    `remote_pattern = "slug"` pairs under `[repos]`
  - [x] Confirm `_read_repos_config()` round-trips correctly

- [x] 2.3 `tests/test_voyages.py` — add injection test
  - [x] Write a voyage with `slug = 'evil"\n[[voyage]]\nslug="injected'`
  - [x] Confirm `write_voyages()` does not raise and produces valid TOML
  - [x] Confirm `read_voyages()` on the output returns exactly one entry with
    the literal slug string intact

- [x] 2.4 `tests/test_git_context.py` — add injection test
  - [x] Write a repos config with a value containing `"` and `\n`
  - [x] Confirm the file is valid TOML after write

---

## 3. Pricing hash bypass — pricing.py

- [x] 3.1 `src/halyard/pricing.py`
  - [x] Change `_check_pricing_hash(body)` signature to `_check_pricing_hash(body) -> bool`
    (it may already return bool — verify)
  - [x] In `update_pricing()`, capture the return value:
    ```python
    hash_changed = _check_pricing_hash(body)
    ```
  - [x] If `hash_changed` and not `accept_changed` flag:
    - Print the old vs new hash to stdout
    - If `sys.stdin.isatty()`: prompt "Accept changed pricing table? [y/N]"
      and abort if user answers N or hits Enter
    - If not a TTY: print error and `raise typer.Exit(code=1)` — instruct
      user to pass `--accept-changed`

- [x] 3.2 `src/halyard/cli.py` — `update-pricing` command
  - [x] Add `accept_changed: bool = typer.Option(False, "--accept-changed")`
    parameter
  - [x] Pass it through to `update_pricing(accept_changed=accept_changed)`

- [x] 3.3 `tests/test_pricing.py`
  - [x] Test: changed hash + TTY → prompts user (mock `sys.stdin`)
  - [x] Test: changed hash + no TTY + no flag → exits non-zero
  - [x] Test: changed hash + `--accept-changed` → proceeds without prompt
  - [x] Test: unchanged hash → proceeds silently (existing behaviour)

---

## 4. `_session_line_hash` produces wrong hashes — outcomes.py + ai_log.py

- [x] 4.1 `src/halyard/ai_log.py`
  - [x] Add `_raw_hash: str | None = field(default=None, repr=False, compare=False)`
    to `AiSession` dataclass
  - [x] In `_parse_session_line()` (or wherever `s` lines are parsed):
    immediately after constructing the `AiSession`, set:
    ```python
    session._raw_hash = session_hash(raw_line)
    ```
    before any amendment folding occurs
  - [x] Confirm `_raw_hash` is excluded from `to_log_line()` serialization
    (it must not appear in the log)
  - [x] Confirm `_raw_hash` is excluded from `==` comparison (the `compare=False`
    field param handles this)

- [x] 4.2 `src/halyard/outcomes.py`
  - [x] Update `_session_line_hash(project_dir, session)` to:
    ```python
    def _session_line_hash(session: AiSession) -> str:
        return session._raw_hash or session_hash(session.to_log_line())
    ```
  - [x] Remove the `project_dir` argument (no longer needed)
  - [x] Update all call sites

- [x] 4.3 `tests/test_outcomes.py`
  - [x] Test: parse a session line → apply an amendment that changes `project`
    → call `_session_line_hash` → confirm hash matches `session_hash(original_raw_line)`
  - [x] Test: full round-trip — write session → amend → `outcome sync` → re-parse
    → confirm `pr_ref` and `pr_state` are present in the re-parsed session

---

## 5. Stale SQLite cache — db.py

- [x] 5.1 `src/halyard/db.py`
  - [x] Find the `INSERT OR IGNORE` statement in `_sync_sessions`
  - [x] Change to `INSERT OR REPLACE` (SQLite `REPLACE` = delete + insert,
    preserves no rowid stability — verify downstream code does not depend on
    stable rowids)
  - [x] If rowid stability is required: use
    `INSERT INTO ... ON CONFLICT(session_id) DO UPDATE SET col=excluded.col, ...`
    for each non-key column instead
  - [x] Verify the `outcomes` and `pr_cache` tables use the same strategy for
    their own upserts

- [x] 5.2 `tests/test_db.py`
  - [x] Test: sync log → amend one session (change project) → re-sync →
    confirm cache row `project` column matches the amended value
  - [x] Test: sync log → `outcome sync` (add `pr_ref`) → re-sync →
    confirm `pr_ref` appears in the cache row

---

## 6. Datetime timezone normalization — collectors + claude_code.py

- [x] 6.1 Audit all collectors — confirm each uses `datetime.now()` (local naive)
  - [x] `src/halyard/collectors/cursor.py` — read and confirm
  - [x] `src/halyard/collectors/gemini.py` — read and confirm
  - [x] `src/halyard/collectors/codex.py` — read and confirm
  - [x] `src/halyard/collectors/vscode.py` — read and confirm if it exists

- [x] 6.2 `src/halyard/collectors/claude_code.py`
  - [x] `record_session_start()`: change `datetime.now(UTC)` to `datetime.now()`
    (local naive). Remove the `from datetime import UTC` import if unused.
  - [x] Remove the Z-suffix from the stored JSON: store
    `"start": datetime.now().isoformat()` instead of UTC ISO with Z
  - [x] `_read_session_state()`: simplify — remove the Z detection and UTC
    offset conversion. Parse the stored string as a plain `datetime.fromisoformat`
  - [x] Confirm `_read_from_transcript(since=start)` still works correctly —
    transcript timestamps are UTC (from the Claude Code JSONL), so the `since`
    comparison must convert `start` to UTC before comparing. Update the
    comparison logic if needed.

- [x] 6.3 `src/halyard/orchestration.py`
  - [x] Confirm timer `started` timestamps use `datetime.now()` — no change
    expected, but verify

- [x] 6.4 `tests/test_v1_collectors.py` (or add new test file)
  - [x] Test: session written by `claude_code` collector and session written by
    `cursor` collector on the same simulated evening both have
    `session.start.date() == datetime.now().date()` (no off-by-one at midnight)
  - [x] Test: `_read_session_state` round-trips a local naive datetime without
    timezone conversion

---

## 7. OS declaration — pyproject.toml + README

*(Most work done in task 1.2 and 1.3 — confirm completeness here)*

- [x] 7.1 `pyproject.toml` — verify OS classifiers added (from task 1.2)
- [x] 7.2 `README.md` — verify platform note added (from task 1.3)
- [x] 7.3 `README.md` — confirm WSL2 mention includes a brief note that the
  Halyard service install (`halyard install-service`) is macOS-only (uses
  `launchctl` / plist)

---

## 8. Regression suite and final checks

- [x] 8.1 Run full test suite: `uv run pytest` — must be ≥ 921 passed, 0 failed
- [x] 8.2 Run `uv run ruff check .` — clean
- [x] 8.3 Run `uv run ruff format --check .` — clean
- [x] 8.4 Run `uv run mypy src` — clean
- [x] 8.5 Manual smoke test:
  - [x] `pipx install halyard` in a clean venv → `halyard init` → `halyard doctor`
  - [x] `halyard update-pricing` with a hash-changed table → confirm prompt fires
  - [x] Create a voyage with a slug containing `"` → confirm `voyages.toml` is valid

---

## 9. Update docs

- [x] 9.1 `docs/current-direction.md` — add v2.29 to build sequence, mark shipped
- [x] 9.2 `openspec/project.md` — add v2.29 entry after v2.28
- [x] 9.3 `docs/PRD-halyard.md` — update Pre-Ship Hardening section (if added)
