# Changelog

All notable changes to Halyard will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **v2.26 — Friends of the Sea:** One sea creature per completed project,
  auto-assigned by personality (Whale, Sea Turtle, Dolphin, Octopus, Clownfish,
  Shark, Coral Reef, Seal). Projects progress through nautical voyage stages:
  Anchors Aweigh → Making Headway → Rounding the Mark → Flying Colors →
  Shipshape · Moored. Auto-completes when sessions hit target or after
  configurable inactivity. New `voyages.toml` data file. New commands:
  `halyard voyage` (list), `halyard voyage complete <slug>`,
  `halyard voyage set <slug> [--sessions N] [--inactivity N]`.
  Friends of the Sea panel added to The Bridge dashboard.
- **v2.26 — Passport:** One stamp per AI tool first used, shown in Captain's
  Quarters on The Bridge and in `halyard honors`. Known tools get a named icon
  (🤖 Claude Code, 🖱️ Cursor, ♊ Gemini CLI, 📦 Codex, ✏️ Manual); unknown
  tools get a generic wrench stamp.
- **v2.25 — Honors and Achievements:** `halyard honors` displays a full service
  record: rank (Deckhand → Commodore, based on attributed session count),
  stripes (watch streak), gold stripe (30+ consecutive clean-watch days), proof
  score, and eight medals (Eight Bells, Full Sail, Clean Manifest, Lighthouse,
  Signal Master, Harbor Master, Fair Winds, Rescue at Sea). Captain's Quarters
  panel added to The Bridge dashboard. Pure read layer — no new data formats.

## [0.2.0] — 2026-05-09

### Added

- **v2.18 — Project registry:** `~/.halyard/projects` stores one absolute
  project path per line.  `halyard init` registers the project automatically.
  `halyard db sync` reads the registry as its primary discovery source and
  falls back to CWD for unregistered projects.  New commands:
  `halyard projects list`, `halyard projects forget <path>`,
  `halyard projects add <path>`.
- **v2.18 — SQLite schema migrations:** `cache.db` now carries
  `PRAGMA user_version`.  Every schema change ships a forward migration in
  `_MIGRATIONS`.  Destructive changes use the `REQUIRES_RESET` sentinel, which
  exits with a clear message asking the user to run
  `halyard db reset && halyard db sync`.  No plain-text data is ever lost.
- **v2.18 — Content-addressed session ID:** The SQLite session primary key is
  now `sha256(start|end|tool|model|input_tok|output_tok)`, stable across `a`
  amendment records.  Amending a session's project attribution no longer
  creates a duplicate cache row.
- **v2.18 — Invoice front-matter rates:** `invoice.md.j2` now writes a
  `template_version: 2` marker and a `rates:` block to the YAML front-matter.
  `audit_invoices` reads front-matter rates first (trust label `structured`);
  falls back to regex parsing for pre-v2.18 invoices (trust label `inferred`).
- **v2.17 — Log integrity:** `ai-sessions.log` supports `a <hash> key=value`
  amendment records for post-hoc attribution correction without mutating
  original `s` lines.  `parse_sessions` folds amendments in file order;
  last-write-wins per key.  Allowed keys: `project`, `source`,
  `confirmed_at`, `note`.
- **v2.17 — File locking:** `locked_file(path, mode)` context manager
  (`fcntl.flock`) wraps all log mutators — `append_session`, timeclock
  clock-in/clock-out, invoice counter — so concurrent writers never interleave.
- **v2.16 — Dashboard token auth:** Per-install 32-byte secret at
  `~/.halyard/dashboard.token` (mode `0600`).  Cookie + `X-Halyard-Token`
  header validated on every POST.  Wrong `Host` → 400; cross-origin → 403;
  bad token → 401; oversized body → 413.
- `halyard init` — scaffolds a new project with `halyard.toml`, `clients.toml`,
  `projects.toml`, `time.timeclock`, `invoices/`, and `.gitignore`.
  Auto-detects business name from `git config user.name`.
  Auto-installs hooks for any AI tool found on PATH.
- `halyard dashboard` — local Glass Cockpit showing sessions, cost, token
  totals, project attribution, active timer, and collector health.
- `halyard tui` — terminal dashboard (Textual).
- `halyard doctor` — diagnoses hooks, log, hub, and first-capture readiness.
- `halyard setup` — guided first-run setup.
- `halyard assign-unattributed` — interactive triage for sessions without
  project attribution.
- `halyard record-session` / `halyard sample-session` — manual and demo capture.
- `halyard db sync` / `halyard db reset` — SQLite read-model cache management.
- Publish workflow: releasing a `v*.*.*` tag publishes to PyPI via trusted
  publishing (no API token stored in secrets).

### Changed

- `halyard init` next-steps message only references implemented commands.
- `halyard init` preserves existing `.gitignore` and appends only missing
  Halyard ignore patterns.
- CI matrix extended to Python 3.11, 3.12, and 3.13.
- GitHub Actions updated to `actions/checkout@v4` and `actions/setup-python@v5`.
- `halyard init` hook-install output now separates "not on PATH" (dim, expected)
  from "install failed" (yellow, needs attention).

## [0.0.1] — 2026-05-06

### Added

- Initial project scaffold and OpenSpec change for v0.
- CLI command surface (stubbed): `init`, `log`, `start`, `stop`, `invoice`.
- Project documentation: README, MIT LICENSE, agent system prompt, default
  invoice template.
- Continuous integration: ruff lint + format check, mypy strict on `src/`,
  pytest with coverage, on every push and pull request.
