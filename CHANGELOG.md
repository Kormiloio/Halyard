# Changelog

All notable changes to Halyard will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `halyard init` command — scaffolds a new Halyard project with `halyard.toml`,
  `clients.toml`, `projects.toml`, `time.timeclock`, `invoices/`, and
  `.gitignore`. (v0 task 2.3)
- `halyard dashboard` command — starts a local Glass Cockpit dashboard showing
  AI sessions, cost, token totals, project attribution, active timer state, and
  collector health.
- `halyard record-session` and `halyard sample-session` commands for manual,
  Codex/local, and demo AI usage capture.
- Reusable AI report and dashboard health services shared by CLI reporting and
  the local dashboard.
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
