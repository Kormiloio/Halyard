# Tasks: v2.20 — Security Remediation

All findings from Adrian's targeted vulnerability scan. All tasks completed
by Kai. 39 new tests added.

## Spec & design
- [x] Write proposal.md
- [x] Write specs/security-fixes.md
- [x] Write design.md

---

## H-1: Origin header validation (4 tests)
- [x] Extract Origin header in `dashboard.py do_POST`
- [x] Build allowed-origins set from bound host:port
- [x] Return 403 FORBIDDEN for disallowed origins before reading request body
- [x] `test_post_cross_origin_returns_403`
- [x] `test_post_no_origin_allowed`
- [x] `test_post_localhost_origin_allowed`
- [x] `test_post_127_origin_allowed`

## H-2: OpenAI base URL validation (6 tests)
- [x] Implement `_validate_base_url(url: str) -> None` in collector module
- [x] Accept https:// (any host), http://localhost, http://127.0.0.1, http://[::1]
- [x] Raise LogAgentError for file://, data://, arbitrary HTTP
- [x] Call validation before constructing any OpenAI client
- [x] `test_validate_base_url_https_accepted`
- [x] `test_validate_base_url_localhost_accepted`
- [x] `test_validate_base_url_file_scheme_rejected`
- [x] `test_validate_base_url_data_scheme_rejected`
- [x] `test_validate_base_url_http_external_rejected`
- [x] `test_validate_base_url_not_set_skipped`

## M-1: Hook payload sanitization (4 tests)
- [x] Implement `_sanitize_field(value: str) -> str` — replace whitespace and = with _
- [x] Apply to tool and model values from hook payloads before AiSession construction
- [x] `test_sanitize_whitespace_replaced`
- [x] `test_sanitize_equals_replaced`
- [x] `test_sanitize_clean_value_unchanged`
- [x] `test_hook_payload_sanitization_end_to_end`

## M-2: Encoding documentation (0 new tests — documentation only)
- [x] Add docstring block in `ai_log.py` documenting note/resume_command encoding contract
- [x] Document round-trip ambiguity (underscore vs encoded space)

## M-3: Slug validation (5 tests)
- [x] Compile `^[a-z0-9][a-z0-9-]{0,63}$` as module-level constant in `config.py`
- [x] Apply at TOML load time; skip invalid slugs with rich warning
- [x] `test_valid_slug_accepted`
- [x] `test_slug_with_uppercase_rejected`
- [x] `test_slug_with_spaces_rejected`
- [x] `test_slug_starting_with_hyphen_rejected`
- [x] `test_slug_too_long_rejected`

## M-4: Invoice path traversal guard (4 tests)
- [x] After constructing candidate path, call `path.resolve()` and compare against `(project_dir / "invoices").resolve()`
- [x] Raise InvoiceError if resolved path is outside invoices/ directory
- [x] `test_normal_invoice_path_accepted`
- [x] `test_traversal_path_rejected`
- [x] `test_traversal_via_symlink_rejected`
- [x] `test_invoice_error_raised_before_any_write`

## M-5: Quarantine log newline sanitization (3 tests)
- [x] In `_write_quarantine()`, call `error.replace("\n", " ")` before formatting
- [x] `test_quarantine_newline_in_error_replaced`
- [x] `test_quarantine_clean_error_unchanged`
- [x] `test_quarantine_multiline_error_single_line_written`

## L-1: Jinja2 autoescape documentation (0 new tests — comment only)
- [x] Add inline comment above `Environment(autoescape=False, ...)` in `invoicing.py`

## L-2: launchctl unload exit handling (3 tests)
- [x] Use `check=False` on `subprocess.run(["launchctl", "unload", ...])`
- [x] Print warning to stderr on non-zero exit code
- [x] Call `plist_path.unlink(missing_ok=True)` unconditionally
- [x] `test_launchctl_nonzero_prints_warning`
- [x] `test_plist_removed_on_nonzero_exit`
- [x] `test_plist_removed_on_zero_exit`

## L-3: Atomic writes in attribution functions (6 tests)
- [x] `assign_unattributed_sessions()` — tmp-then-rename
- [x] `confirm_session_attributions()` — tmp-then-rename
- [x] `backfill_window()` — tmp-then-rename
- [x] `test_assign_unattributed_write_is_atomic`
- [x] `test_confirm_attributions_write_is_atomic`
- [x] `test_backfill_window_write_is_atomic`
- [x] `test_assign_unattributed_no_partial_state_on_interrupt`
- [x] `test_confirm_attributions_no_partial_state_on_interrupt`
- [x] `test_backfill_window_no_partial_state_on_interrupt`

## L-4: pip-audit in CI (0 new tests — config only)
- [x] Add `pip-audit` to `[project.optional-dependencies.dev]` in `pyproject.toml`
- [x] Add pip-audit step to CI workflow after test step

## L-5: halyard init writes .halyard/ to .gitignore (4 tests)
- [x] `halyard init` appends `.halyard/` to generated .gitignore
- [x] `test_init_gitignore_contains_halyard_dir`
- [x] `test_init_gitignore_created_if_absent`
- [x] `test_init_gitignore_appended_if_present`
- [x] `test_init_gitignore_not_duplicated_if_already_present`

## Quality
- [x] Run full test suite — all passing (39 new tests, 2026-05-08)
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
