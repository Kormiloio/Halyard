# Tasks

Implementation checklist for v2.11 — Hook Normalization and Auto-Install.

## 1. Command renaming

- [x] 1.1 Register `install-hook-claude` as canonical name.
- [x] 1.2 Register `install-hook-cursor` as canonical name.
- [x] 1.3 Register `install-hook-gemini` as canonical name.
- [x] 1.4 Keep old names as hidden aliases.

## 2. Shared install helpers

- [x] 2.1 Extract `_do_install_hook_claude(global_)` from command body.
- [x] 2.2 Extract `_do_install_hook_cursor()` from command body.
- [x] 2.3 Extract `_do_install_hook_gemini()` from command body.

## 3. Auto-install on init

- [x] 3.1 Add `_auto_install_detected_hooks()` using `shutil.which()`.
- [x] 3.2 Wire into `halyard init` after `scaffold_project()`.
- [x] 3.3 Wrap each installer in `OSError` catch so init never aborts.
- [x] 3.4 Print found/not-found summary at end of init.

## 4. Tests

- [x] 4.1 Verify existing `test_init.py` tests pass with auto-install wired in.
