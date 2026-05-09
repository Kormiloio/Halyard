# Changelog

All notable changes to Halyard will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **v2.17 — Log Integrity:** `ai-sessions.log` now supports `a` amendment
  records (`a <hash> key=value …`) for post-hoc attribution correction without
  mutating the original `s` lines.  `parse_sessions` folds amendments in file
  order; last-write-wins per key.  Allowed keys: `project`, `source`,
  `confirmed_at`, `note`.
- **v2.17 — File locking:** `locked_file(path, mode)` context manager
  (`fcntl.flock`) wraps all log mutators — `append_session`, timeclock
  clock-in/clock-out, and the invoice counter — so concurrent writers never
  interleave.
- **v2.16 — Dashboard token auth:** Each Halyard install now generates a
  per-install 32-byte secret at `~/.halyard/dashboard.token` (mode `0600`).
  The token is set as a cookie on every dashboard page load and validated on
  every POST.  POSTs with a wrong `Host` header return 400; cross-origin POSTs
  return 403; missing/invalid tokens return 401; bodies over 8192 bytes return
  413.  **Breaking:** pre-v2.16 direct POST integrations (none documented) will
  receive 401 until updated to include the token cookie or `X-Halyard-Token`
  header.

### Added

- `halyard init` command — scaffolds a new Halyard project with `halyard.toml`,
  `clients.toml`, `projects.toml`, `time.timeclock`, `invoices/`, and
  `.gitignore`. (v0 task 2.3)
- `halyard dashboard` command — starts a local Glass Cockpit dashboard showing
  AI sessions, cost, token totals, project attribution, active timer state, and
  collector health.
- `halyard record-session` and `halyard sample-session` commands for manual,
  Codex/local, and demo AI usage capture.
- `halyard assign-unattributed` command and dashboard Needs Attention panel for
  assigning AI sessions that do not yet have project attribution.
- Reusable AI report and dashboard health services shared by CLI reporting and
  the local dashboard.
- Product requirements and OpenSpec stories for an org admin dashboard covering
  manager, CIO, governance, and finance rollups.
- Auto-detection of business name from `git config user.name` during `init`.
  Falls back to a generic placeholder if git is unavailable or unset.
- `.DS_Store` to the project `.gitignore` written by `halyard init`.

### Changed

- `halyard init` next-steps message now only references implemented commands;
  unimplemented commands are listed under "more commands will land later" so
  users aren't pointed at stubs.
- `halyard init` now preserves existing `.gitignore` files and appends only
  missing Halyard ignore patterns.

## [0.0.1] — 2026-05-06

### Added

- Initial project scaffold and OpenSpec change for v0.
- CLI command surface (stubbed): `init`, `log`, `start`, `stop`, `invoice`.
- Project documentation: README, MIT LICENSE, agent system prompt, default
  invoice template.
- Continuous integration: ruff lint + format check, mypy strict on `src/`,
  pytest with coverage, on every push and pull request.
