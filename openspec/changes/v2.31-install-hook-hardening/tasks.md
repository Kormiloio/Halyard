# v2.31 Install-Hook Hardening — Tasks

---

## 1. Cross-file dedup in `_do_install_hook_claude()`

- [x] 1.1 `src/halyard/cli.py`
  - [x] In `_do_install_hook_claude()`, determine the "other" settings path
  - [x] Before writing, check if proposed command keys overlap with other file
  - [x] If match found: print warning naming `other_path`, return without writing
  - [x] If `other_path` does not exist or is unreadable: proceed normally

- [x] 1.2 `tests/test_hook_auto_install_v218.py`
  - [x] Test: global hook present → local install skipped
  - [x] Test: local hook present → global install skipped
  - [x] Test: neither file has hook → install proceeds
  - [x] Test: other file absent → install proceeds
  - [x] Test: other file has no hooks → install proceeds

---

## 2. Setup wizard scope question

- [x] 2.1 `src/halyard/cli.py` — `setup_cmd()` wizard
  - [x] When Claude selected without `--global-claude` and TTY available, prompt
    "Do you work on more than one project? [y/N]"
  - [x] "y" → `global_=True`; Enter/n → `global_=False`
  - [x] Non-TTY: skip prompt, use `global_=False`

---

## 3. `halyard doctor` duplicate detection

- [x] 3.1 `src/halyard/doctor.py`
  - [x] Add `_claude_hook_duplicate_check(current: Path) -> DoctorCheck | None`
  - [x] Uses `_cmd_key()` normalizer to compare local vs global hook commands
  - [x] Returns `hook.claude.duplicate` warning if overlap found

- [x] 3.2 `tests/test_doctor.py`
  - [x] Test: both files contain hook → warning appears
  - [x] Test: only global file has hook → no duplicate warning
  - [x] Test: neither file exists → no exception, no warning

---

## 4. Regression suite and final checks

- [x] 4.1 918 tests passing (pre-existing test_db and test_manual_sessions excluded)
- [x] 4.2 `uv run ruff check .` — clean
- [ ] 4.3 `uv run ruff format --check .` — clean
- [ ] 4.4 `uv run mypy src` — clean
- [ ] 4.5 Manual smoke test

---

## 5. Update docs

- [x] 5.1 `openspec/project.md` — added v2.31 entry
- [x] 5.2 `docs/current-direction.md` — added v2.31 to build sequence
