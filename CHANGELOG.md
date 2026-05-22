# Changelog

All notable changes to Halyard will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] — 2026-05-22

### Fixed

- **Gemini phantom sessions:** a stale `~/.halyard/gc-session` file from a
  prior session could be re-read on every `gc-hook` invocation, producing
  multi-day phantom entries with absurd `wall_seconds`. `handle_agent_stop()`
  now refuses to write a session whose implied wall time exceeds 12 hours
  and deletes the stale state file.
- **VS Code extension auto-tracking:** the v2.32 extension required users
  to manually run `halyard.startAIWork` before any editing time was
  captured. New `halyard.autoTrack` setting (default `true`) auto-starts a
  session on activation and on the first activity event in an idle
  workspace.
- **v2.16 — Templates not packaged in wheel (C1):** `pip install halyard &&
  halyard invoice <client>` raised `TemplateNotFound` because
  `templates/invoice.md.j2` lived outside `src/halyard/` and was never
  declared as package data. Templates moved to `src/halyard/templates/`;
  the loader now resolves via `Path(__file__).parent / "templates"`.
  CI now installs the wheel in a clean venv and renders an invoice on
  every push to catch this class of bug going forward.
- **v2.16 — `service_status` reported the wrong port:** when a user
  installed the dashboard with `halyard service install --port 7777`,
  `halyard service status` still reported `:7432`. `service_status` now
  parses the installed plist's `ProgramArguments` and reports the actual
  port; falls back to the default with a one-line warning if the plist
  is malformed.
- **Release metadata:** package version now matches the next public release
  tag, so the wheel builds as `halyard-0.2.1` instead of reusing the already
  tagged `0.2.0` artifact name.
- **Documentation links:** docs index and README no longer point at deleted
  PRD/OpenSpec files.

### Changed

- **Cross-platform file locking:** `locked_file()` now dispatches between
  `fcntl.flock` (POSIX), `msvcrt.locking` (Windows), and a thread-only
  fallback (with a one-time warning) at import time. The README's
  Windows-not-supported note has been removed.
- **`ai-sessions.log` reader streams line-by-line:** `parse_sessions()`
  and `unattributed_log_count()` no longer load the whole log into memory;
  memory is bounded by the longest single line. Behaviour-equivalent;
  same quarantine semantics.
- **Free-text encoding for `note` and `resume_command`:** new writes use
  percent-encoding (`urllib.parse.quote`) instead of underscore substitution,
  so literal underscores in user input no longer collide with encoded
  spaces. Pre-existing log lines without `%` characters continue to decode
  with the legacy rule. `session_hash` of historical lines is unchanged
  so amendment records keep working.
- **Metadata field escaping in `to_log_line`:** the previously-unescaped
  `project`, `user`, `billing`, `job_id`, `source`, `attr_method`, `tags`,
  `session_id`, `model_breakdown`, `branch`, `pr_ref`, `pr_state`, and
  `outcome_resolved_at` fields are now sanitised through `_safe_field`.
  Whitespace and `=` in any of these can no longer split or smuggle into
  the space-delimited log line.
- **Narrow exception types in collectors:** the five `except Exception:`
  swallows in `collectors/gemini_history.py` were tightened to specific
  tuples (`OSError`, `json.JSONDecodeError`, `UnicodeDecodeError`,
  `KeyError`, `TypeError`, `ValueError`, `AttributeError`). Programmer
  bugs no longer hide as silent `None` returns.
- **Repositioned framing:** README lead, `pyproject.toml` description, and
  the root CLI `--help` epilog now all read *"Your AI work leaves a trail.
  Halyard makes that trail legible, auditable, and client-safe."*
- **Dashboard service executable resolution:** `halyard service install`
  now uses the same trusted executable resolver as hook installation instead
  of persisting an arbitrary PATH hit into the LaunchAgent plist.
- **Doctor integrity reporting:** `halyard doctor` now evaluates
  state-integrity mode from the active project or hub, and honors existing
  sidecars, so hash/HMAC state no longer appears as `mode=off`.

### Added

- **State integrity (opt-in):** new `halyard.state_integrity` module adds
  optional SHA-256 verification of trusted state files
  (`~/.halyard/active`, `~/.halyard/hub`). Off by default — enable with
  `state_integrity = "hash"` in `halyard.toml` or
  `HALYARD_STATE_INTEGRITY=hash`. Tampered files raise `IntegrityError`,
  which `read_active_project()` and `find_hub()` catch and fail soft on
  (return `None` and log) so a corrupt state file does not crash every
  collector hook. `halyard doctor` reports the active mode.
- **`halyard init --no-interactive`:** skip hook auto-installation in CI
  and unattended setup.
- **CI install-test workflow:** `.github/workflows/install-test.yml`
  builds the wheel and exercises `halyard --version`, `halyard init`, and
  `halyard invoice` in a clean venv on Python 3.11/3.12/3.13.
- **Dashboard pre-v2.16 POST integrations note:** any external script
  POSTing to `http://127.0.0.1:7432/api/{start,stop}` must now present
  the per-install token from `~/.halyard/dashboard.token` via cookie or
  `X-Halyard-Token` header, with a matching `Host` value of
  `127.0.0.1:<port>`. Scripts written against the unauthenticated
  pre-v2.16 dashboard will fail with HTTP 401/400 until updated.

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
- `halyard dashboard` — local The Bridge showing sessions, cost, token
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
