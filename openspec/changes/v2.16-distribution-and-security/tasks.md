# Tasks

Implementation checklist for v2.16 — Distribution and Security.

## 1. Template packaging (C1)

- [ ] 1.1 Create `src/halyard/templates/` directory.
- [ ] 1.2 Move `templates/invoice.md.j2` (and any sibling Jinja templates) into it.
- [ ] 1.3 Update `_template_dir()` in `invoicing.py` to use `Path(__file__).parent / "templates"`.
- [ ] 1.4 Add `force-include` entry to `pyproject.toml` for the templates dir.
- [ ] 1.5 Verify `uv build` produces a wheel containing the templates (`unzip -l dist/*.whl | grep templates`).
- [ ] 1.6 Update test_invoicing fixtures if they relied on the old path.

## 2. Dashboard auth (C2)

- [ ] 2.1 Add `_token_path()` and `_load_or_create_token()` helpers in `service.py`.
- [ ] 2.2 In `dashboard.py do_GET`, set `halyard_token` cookie on `/` and `/index.html` responses.
- [ ] 2.3 In `dashboard.py do_POST`, validate `Host` header against the bound `host:port`.
- [x] 2.4 Validate `Origin` / `Referer` headers if present.
  — Implemented in v2.20 (H-1): Origin header validation; cross-origin POSTs return 403.
- [ ] 2.5 Validate token via cookie or `X-Halyard-Token` header.
- [ ] 2.6 Return 400 / 401 / 403 with terse JSON bodies on rejection.
- [ ] 2.7 Cap `Content-Length` at 8192 bytes; return 413 if exceeded.

## 3. Service port reporting (M6) and init bypass

- [ ] 3.1 `install_service` writes `--port=<n>` into the plist `ProgramArguments`.
- [ ] 3.2 `service_status` parses the installed plist for the port.
- [ ] 3.3 Fallback to `DASHBOARD_PORT` constant with a warning if plist is malformed.
- [ ] 3.4 Add `halyard init --no-interactive` flag (no prompts; defaults from flags).

## 4. CI install gate (L7)

- [ ] 4.1 Add `.github/workflows/install-test.yml` with Python 3.11/3.12/3.13 matrix.
- [ ] 4.2 Build wheel, install in clean venv, run smoke commands.
- [ ] 4.3 Make the workflow required for merging to main.

## 5. Tests

- [ ] 5.1 `tests/test_dashboard_security.py` — POST without token returns 401.
- [ ] 5.2 POST with token but wrong Host returns 400.
- [ ] 5.3 POST with token but cross-origin Referer returns 403.
- [ ] 5.4 POST with valid token + Host succeeds.
- [ ] 5.5 POST with Content-Length > 8192 returns 413.
- [ ] 5.6 `tests/test_service.py` — `install_service` with custom port; status reports the right URL.
- [ ] 5.7 Regression test for invoice rendering after templates move.

## 6. Positioning update

- [ ] 6.1 Update README lead paragraph to "AI Work Intelligence" framing per
  post-review-roadmap.md.
- [ ] 6.2 Update `pyproject.toml` description field to match.
- [ ] 6.3 Update CLI `--help` epilog on the root app.

## 7. Documentation

- [ ] 7.1 Document the per-install token in `halyard service status` output.
- [ ] 7.2 Document `halyard init --no-interactive` for CI users.
- [ ] 7.3 Note in CHANGELOG that pre-v2.16 dashboard POST integrations
  (none documented) will break with 401.
