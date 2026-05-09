# v2.20 Design — Security Remediation

## Approach

All fixes are surgical. No new architectural layers were introduced. No new
dependencies were added. All changes preserve the existing log format and API
compatibility.

---

## H-1: Origin header validation

Implemented in `dashboard.py do_POST`. The handler extracts the `Origin`
header and compares it against the set of allowed origins: `http://localhost`,
`http://127.0.0.1`, and their port-qualified variants matching the bound port.
Requests with a disallowed Origin return 403 immediately, before the request
body is read.

Absence of an Origin header is treated as same-origin (consistent with browser
behavior for non-CORS requests).

---

## H-2: OpenAI base URL validation

A `_validate_base_url(url: str) -> None` function in the relevant collector
module checks the URL scheme before constructing any OpenAI client. Accepted:
`https://` (any host), `http://localhost`, `http://127.0.0.1`, `http://[::1]`.
All other schemes and hosts raise `LogAgentError` with a descriptive message.

---

## M-1: Hook payload sanitization

The `_sanitize_field(value: str) -> str` helper replaces any whitespace
character or `=` with `_`. Applied to `tool` and `model` values from hook
payloads before they are passed to `AiSession` construction. This prevents
log-format injection via crafted tool or model strings.

---

## M-2: Encoding documentation

No code change. An inline docstring block is added to `ai_log.py` in the
`to_log_line()` / `from_log_line()` region documenting the `note` and
`resume_command` encoding contract, including the round-trip ambiguity. This
satisfies the finding without altering the log format.

---

## M-3: Slug validation

`^[a-z0-9][a-z0-9-]{0,63}$` compiled as a module-level constant in
`config.py`. Applied at TOML load time before any slug is used to construct a
file path. Invalid slugs emit a `rich` warning and are excluded from the
loaded config.

---

## M-4: Invoice path traversal

After constructing the candidate invoice path, `path.resolve()` is called and
compared against `(project_dir / "invoices").resolve()`. If the resolved path
is not under the expected directory, `InvoiceError` is raised before any I/O
or subprocess call.

---

## M-5: Quarantine log newlines

`_write_quarantine()` calls `error.replace("\n", " ")` before formatting the
error comment line. This prevents multi-line error messages from corrupting
the quarantine log's line-oriented format.

---

## L-1: autoescape comment

A single inline comment added above the `Environment(autoescape=False, ...)`
call in `invoicing.py`:
```python
# autoescape=False: intentional — templates render Markdown, not HTML.
# Escaping would corrupt Markdown syntax (e.g., < > in code blocks).
```

---

## L-2: launchctl exit handling

`subprocess.run(["launchctl", "unload", ...], check=False)` — the return code
is inspected; if non-zero, a warning is printed to stderr. The plist removal
(`plist_path.unlink(missing_ok=True)`) runs unconditionally after the
launchctl call.

---

## L-3: Atomic writes

`assign_unattributed_sessions()`, `confirm_session_attributions()`, and
`backfill_window()` each write to a `.tmp` sibling of the target file and then
call `Path.rename()`. POSIX `rename()` is atomic on the same filesystem.

---

## L-4: pip-audit

Added to `[project.optional-dependencies.dev]` in `pyproject.toml`. CI step
added after the test step:
```yaml
- name: Audit dependencies
  run: pip-audit
```

---

## L-5: .gitignore

`halyard init` appends `.halyard/` to the `.gitignore` it generates (or
creates) in the new project directory.

---

## Test coverage

39 new tests added across:
- `tests/test_dashboard_security.py` — H-1 (4 tests)
- `tests/test_base_url_validation.py` — H-2 (6 tests)
- `tests/test_hook_sanitization.py` — M-1 (4 tests)
- `tests/test_config_slug_validation.py` — M-3 (5 tests)
- `tests/test_invoice_path_traversal.py` — M-4 (4 tests)
- `tests/test_quarantine.py` — M-5 (3 tests, extended)
- `tests/test_service.py` — L-2 (3 tests, extended)
- `tests/test_attribution_atomic.py` — L-3 (6 tests)
- `tests/test_init.py` — L-5 (4 tests, extended)

All 39 tests pass. ruff and mypy report no new errors.
