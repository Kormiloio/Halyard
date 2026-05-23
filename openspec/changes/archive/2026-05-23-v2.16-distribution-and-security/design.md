# Design

## Templates packaging

Move:
- `templates/invoice.md.j2` → `src/halyard/templates/invoice.md.j2`
- any other Jinja templates currently outside the package

Update `_render_invoice` in `invoicing.py` to:

```python
def _template_dir() -> Path:
    return Path(__file__).parent / "templates"
```

Update `pyproject.toml` to ensure the directory is shipped. Hatch
already includes package data by default for files under the package
root, but be explicit:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/halyard"]

[tool.hatch.build.targets.wheel.force-include]
"src/halyard/templates" = "halyard/templates"
```

User-supplied template overrides (`<project>/templates/`) continue to
work unchanged — the override path is checked before the package
default.

## Dashboard auth

`~/.halyard/dashboard.token` is a 32-byte hex secret created on first
`service install` (or first standalone `halyard dashboard` run) with
mode `0600`.

Request handling:

1. `do_POST` reads `Host` header; reject with 400 if not
   `127.0.0.1:7432` (or whatever port the server bound).
2. Read `Origin` / `Referer` headers. If present and not matching the
   server's own origin, reject with 403.
3. Read `Cookie` header for `halyard_token=<value>` or
   `X-Halyard-Token` header. If missing or mismatch with file, reject
   with 401.
4. Cap `Content-Length` to 8192 bytes; reject with 413 if larger.
5. Otherwise proceed with start/stop logic.

`do_GET` for `/` sets the token cookie:

```
Set-Cookie: halyard_token=<value>; Path=/; HttpOnly; SameSite=Strict
```

This means: a user opening the dashboard in their own browser gets the
cookie automatically; a cross-origin form POST cannot read the cookie
file or the home directory, so it cannot forge the token.

## Service status

`install_service` accepts `port` and writes it into the plist
`ProgramArguments` as `--port=<n>`. `service_status` reads the plist,
extracts the port, and constructs the status URL. If the plist is
malformed or absent, fall back to `DASHBOARD_PORT` constant with a
warning.

## CI install test

New workflow `.github/workflows/install-test.yml`:

```yaml
strategy:
  matrix:
    python: ["3.11", "3.12", "3.13"]
steps:
  - run: uv build
  - run: python -m venv /tmp/venv
  - run: /tmp/venv/bin/pip install dist/*.whl
  - run: /tmp/venv/bin/halyard --version
  - run: /tmp/venv/bin/halyard init --no-interactive ./fixture
  - run: cd ./fixture && /tmp/venv/bin/halyard invoice acme --period 2025-01
```

The `halyard init --no-interactive` path needs a small CLI addition (a
flag suppressing the prompts) — track as task 3.0 below.

## Token rotation

Out of scope for v2.16. If a token is compromised, the user runs
`halyard service uninstall && halyard service install` which generates
a fresh token. Document this in service status output.

## Migration

Existing users of the v2.12 dashboard:
- On first `service install` after upgrading, generate the token if
  missing.
- The cookie is set on next page load. No user action needed.
- Pre-existing `POST` integrations break loudly with 401 — acceptable
  given there are no documented integrations and the endpoints are
  brand new.
