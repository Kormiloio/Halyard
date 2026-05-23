# Proposal: v2.16 — Distribution and Security

## Why

The v2.15 deep code review surfaced two launch-blocking bugs and three
silent risks introduced by the v2.12 dashboard service. They must ship
before any external user, public PyPI release, or demo.

- **C1 — PyPI install breaks invoicing.** `_render_invoice` resolves the
  Jinja template via `Path(__file__).resolve().parents[2] / "templates"`.
  In a wheel install that path is outside the package; `templates/` was
  never declared as package data. First call to `halyard invoice` after
  `pip install halyard` raises `TemplateNotFound`.
- **C2 — Dashboard service has no auth or CSRF protection.** The v2.12
  LaunchAgent binds `127.0.0.1:7432` permanently and exposes
  `POST /api/start` and `POST /api/stop` to any process or browser tab on
  the machine. A drive-by webpage can corrupt a user's billing data via a
  cross-origin form POST.
- **M5 — Unbounded `Content-Length` reads** can be triggered by a hostile
  client.
- **M6 — `service_status` ignores the configured port** and always reports
  the constant.
- **L7 — No CI gate** runs `pip install . && halyard <cmd>` in a clean
  venv. C1 would have been caught immediately by such a test.

## What changes

- Move `templates/` under `src/halyard/templates/` and reference via
  `Path(__file__).parent / "templates"`. Add `[tool.hatch.build]` config
  ensuring the directory is packaged.
- Add a per-install dashboard token at `~/.halyard/dashboard.token`
  (created on first service start). All `POST /api/*` requests require the
  token via cookie or `X-Halyard-Token` header.
- Validate `Host` header is `127.0.0.1:7432`; reject unexpected
  `Origin`/`Referer` to defeat DNS rebinding.
- Cap `Content-Length` to 8 KB in `do_POST`.
- `service_status` parses the installed plist for `--port` and reports
  the actual URL.
- Add a GitHub Actions job that builds the wheel, installs it in a fresh
  Python 3.11 / 3.12 / 3.13 venv, and runs `halyard --version`,
  `halyard init`, and `halyard invoice` against a fixture project.

## What stays the same

- The dashboard remains read-only-by-default (GET serves the rendered
  page). Only state-changing POSTs require the token.
- The plain-text log format and existing CLI surface are untouched.
- No migration of existing user state.

## Out of scope

- TLS for the dashboard. Localhost is sufficient given the token + Host
  validation.
- Multi-user dashboard auth. Still one user per machine.
- Network-exposed dashboard. Still binds `127.0.0.1` only.

## Success criteria

- `pip install <wheel> && halyard invoice <slug>` succeeds in a clean
  Python 3.11 venv with no source tree present.
- A cross-origin POST from `http://attacker.example` to
  `http://127.0.0.1:7432/api/start` is rejected with HTTP 403.
- A POST without the token is rejected with HTTP 401.
- A POST with a bogus `Host` header is rejected with HTTP 400.
- `halyard service status` after `halyard service install --port 7777`
  reports `http://127.0.0.1:7777/`.
- The CI install-test job is green on main.
