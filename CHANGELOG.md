# Changelog

All notable changes to Halyard will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.4] — 2026-09-05

### Fixed

- **The whole-file size cap that hid large Codex rollouts was in every
  collector (v5.34):** 0.2.3 fixed it for Codex and recorded the same shape
  elsewhere as not yet demonstrably losing data. It was. `copilot.py`
  capped at 50 MB directly above a streaming read, so a **135.9 MB Copilot
  chat was silently skipped** while `halyard doctor` reported Copilot
  history present but unimported — with no hint that importing could not
  fix it. These readers stream line by line, so peak memory is the longest
  *line*; a whole-file cap bounds nothing about resource use and only sets
  the size at which a session vanishes, failing precisely where it costs
  most. Copilot, Claude Code, Antigravity and Codex now share one bounded
  reader (16 MiB per line, 1 GiB budget, truncation logged rather than
  silent). Gemini OTel is fixed differently and deliberately: its read was
  already bounded, so only the redundant *rejection* is removed — it had
  turned "read the first 25 MB" into "read nothing". On the machine that
  found this, `halyard import-copilot` went from **2 sessions to 3**.

## [0.2.3] — 2026-09-05

Three fixes to time and token accuracy, all of which were silently
under-reporting. Every one was found by acting on Halyard's own output and
watching it disagree with itself.

### Fixed

- **Large Codex sessions were silently uncapturable (v5.32):** the rollout
  reader capped at 25 MB of *whole file* and yielded nothing above it, so
  the session was skipped with no log line, no warning and no doctor
  signal. Because the reader streams line by line, that cap never bounded
  memory — it only set the size at which a session vanished, and it failed
  exactly where it costs most: short sessions imported fine while long
  agentic runs disappeared. `halyard doctor` would report capture lagging
  and advise `halyard import-codex`, a command that could not fix it. On
  the machine that found this, one session was recorded as 103.8M tokens
  when its rollout held **371.1M** — a 3.6x understatement, and the
  recorded Codex total rose from 148.2M to **419.8M** once fixed. Now
  bounded per line (16 MiB) with a 1 GiB parse budget, and truncation is
  logged rather than silent.

- **The auto-timer counted prompt cadence, not work (v5.26):** the idle
  policy closes a window retroactively at the last activity, so one prompt
  kicking off a two-hour agent turn was closed out from under itself at
  ~30 minutes. The Stop hook's refresh could not rescue it — it returns
  early when no window is open, which is precisely the state the stale
  close leaves behind. Observed: **34 minutes counted for a day whose own
  session log proves 2h20m**. Sessions are now the evidence of record — on
  stop, the timeclock is made to cover the span the session proves, writing
  only uncovered gaps (append-only, never past the session's end, never
  double-billing). Also wired into cursor, gemini and windsurf, which
  previously never touched the auto-timer at all.

### Added

- **`halyard timeclock repair --from-sessions` (v5.33):** reconciles the
  timeclock against the session ledger to recover time lost before v5.26.
  Union semantics, dry-run by default, timestamped backup before any write.
  Sessions longer than the collectors' own 12 h plausibility cap are
  skipped and reported rather than claimed — a long-lived imported session
  is not evidence of continuous work, and claiming one would turn an
  under-count into a much worse over-count. Recovered **72.2 h** (8.4 h →
  80.6 h) on the machine that motivated it.

## [0.2.2] — 2026-09-05

> **Coverage note.** This file is complete through v3.15 and then thins out
> badly: the v4.x and v5.x tracks (roughly 28 changesets) landed without
> changelog entries. What follows adds the user-visible changes from the
> v5.24–v5.31 track; the entries below the `0.2.2` heading from earlier
> tracks are the v3.x work that was already recorded. For the complete
> record of everything between 0.2.1 and 0.2.2, see `openspec/changes/`.
> Reconciling this file properly is tracked as follow-up work.

### Fixed

- **`halyard mcp` failed on a fresh install (v5.30):** the `mcp` extra was
  declared `mcp>=1.2`, which resolves to mcp 2.x, where FastMCP was renamed
  to MCPServer. `mcp.server.fastmcp` does not exist there, so the server
  died on import — and the error was reported as *"the MCP SDK is not
  installed"*, sending you to reinstall an extra you already had. The
  reinstall resolved 2.x again and reproduced the same message. Now pinned
  `mcp>=1.28.1,<2`, and the two failures ("absent" vs "wrong major") report
  differently.
- **A stale hub pointer reported itself as "no hub configured" (v5.29):**
  `~/.halyard/hub` holds an absolute path. If that directory moved, the
  pointer silently stopped resolving and every ambient session diverted to
  `~/.halyard/unattributed.log` (recoverable, but absent from reports)
  while `halyard doctor` blamed a missing configuration. Doctor now
  distinguishes the two and names the path that vanished.
- **`halyard hub <path>` did not exist (v5.29):** doctor advertised it as
  the fix for an unconfigured hub, but a same-named command group shadowed
  it, so the advice could not be run. Implemented as `halyard hub set` /
  `halyard hub show`, matching what the source already documented.
- **A lost hub response reported a successful timer start as a failure
  (v5.31):** the Hub commits the clock-in entry and `~/.halyard/active`
  before sending its response, so a dropped connection left a running timer
  while the client saw only a failure. `halyard start` then reported
  *"Timer already running. Stop it first."* for the timer it had just
  created — advice that stops the work you meant to begin. The client now
  reconciles with the Hub before falling back.
- **Grok CLI sessions logged as Claude/Cursor (v5.25):** foreign-harness
  detection now keeps Grok CLI activity out of the Claude and Cursor
  collectors.
- **Catch-up capture could deadlock (v5.27):** the catch-up anchor is now
  clamped so a stalled import cannot wedge capture.
- **Dependency audit covered only half the tree (v5.30):** CI installed
  `.[dev]`, so the CVE audit never saw the `mcp` extra or anything beneath
  it — mcp, starlette, cryptography, pyjwt, python-multipart, msgpack.
  27 advisories were open there while CI reported the audit green. CI now
  installs and audits the optional surface too.

### Added

- **Antigravity collector (v5.24):** captures Google's agentic IDE from its
  JSONL transcript, quarantined from spend.

### Fixed

- **Capture monitoring blind spot for Cursor and Windsurf (v3.15):** the
  `halyard doctor` capture-coverage canary — which warns when a tool runs but
  Halyard stops recording it — only watched Claude Code, Gemini, Copilot, and
  Codex. Cursor and Windsurf could silently stop capturing with no warning (the
  same failure class as the Gemini outage). The canary now covers them too, using
  a coarse storage-mtime signal (never parsing their internal SQLite/leveldb
  stores, which would just be more fragile scraping) with a wider grace and an
  honestly-qualified, best-effort warning. Baseline-gated and warning-only, so a
  never-used or merely-unused tool does not false-alarm.
- **Gemini sessions counted multiple times (v3.14):** a multi-turn Gemini CLI
  session was over-counted (one observed session counted ~2.5×). The Gemini
  history file is the whole-session record, and both capture paths read all of
  it: the live hook re-parses it every turn and writes the running *cumulative*
  total as that turn's row (so turns sum overlapping snapshots), and
  `import-gemini` appends one more whole-session row that the existing dedup
  missed (different start, no project). A read-time collapse in `parse_sessions`
  now keeps a single canonical row per Gemini session id (resolved from the hook
  row's `session_id` or the import row's `job_id=gemini:<id>`), so every surface
  — report, dashboard, budget, MCP, status — counts each session once. It is
  read-time only (raw lines stay in the log) and so also corrects sessions
  already recorded. Known limitation: a secondary utility/router model
  (`gemini-3.1-flash-lite`) that Gemini shows in `/quit` but does not write to
  the session history remains uncaptured — see `docs/collector-coverage.md`.
- **Gemini CLI sessions silently not captured (v3.8):** Gemini CLI switched
  its on-disk session history from a single-object `session-*.json`
  checkpoint to a line-delimited `session-*.jsonl` rollout, which the
  collector did not understand — no Gemini session had been recorded since
  2026-05-07. The history parser (`gemini_history.py`, used by both
  `halyard import-gemini` and the live hook) now detects `.jsonl` and parses
  it as a bounded stream. Because the rollout re-emits the same assistant
  message many times as it streams, events are deduped by `id` before
  aggregation, so token/tool totals match Gemini's own `/quit` summary
  instead of being inflated ~30×. Discovery now finds `.jsonl` files; the
  legacy `.json` path is unchanged.
- **Gemini live-hook recorded nothing (tz-aware crash, v3.8):** the same
  outage had a second cause on the live-hook side. Gemini's SessionStart
  payload timestamp is now tz-aware (trailing `Z`), so `handle_agent_stop`
  parsed an aware `turn_start` and subtracted naive `datetime.now()`,
  raising `TypeError` that the hook crash-backstop swallowed — every
  `AfterAgent` fire silently recorded nothing and never reset state
  (`AfterModel` was unaffected, so token state still accumulated). The hook
  now normalises the timestamp to local-naive.
- **Claude Code silent under-capture (v3.9):** the Stop hook recorded only the
  current turn (`since = this turn's start`) and relied on `UserPromptSubmit`
  and `Stop` firing in lockstep. When `Stop` was missed for a stretch (common
  in the desktop app), those turns were dropped permanently — an audit found
  one session capturing ~35% of its real tokens. `handle_stop_hook` now anchors
  the transcript read to the last recorded end for the session, so a single
  Stop after a gap back-fills everything since the last row.
- **Importer dedup was working-directory-dependent (v3.11):** the Gemini
  importer built its "already imported" set from the current project + hub but
  writes per-slug, so a run from any other directory (e.g. a scheduled job)
  re-imported everything and created duplicates. It now dedups against the dir
  each session actually routes to, so repeated/scheduled runs are idempotent
  regardless of cwd.
- **Copilot sessions silently not captured (v3.13):** VS Code changed its chat
  session file to an incremental patch log (a `kind:0` snapshot plus
  `kind:1`/`kind:2` key-path updates), with the model output arriving via
  `["requests", N, "response"]` sub-path patches. The importer only applied a
  whole-array `["requests"]` replace, so every recent session looked empty and
  was skipped — a live Copilot review captured nothing. The parser now
  reconstructs the final state from the patches (metadata only; no content).

### Added

- **`halyard doctor` capture-coverage canary (v3.10):** flags a live-capture
  tool (Claude Code, Gemini) whose on-disk session files are newer than its
  last captured ledger row — i.e. the tool ran but capture didn't record it.
  This is the check that was missing when Gemini broke: "hooks installed" was
  green and the drift canary couldn't see a tool producing zero rows. Warning
  only; baseline-gated; 2-day grace.
- **`halyard import-all` + scheduled importer (v3.11):** one idempotent command
  runs the Codex, Copilot, and Gemini importers. `halyard install-import-timer`
  / `uninstall-import-timer` schedule it via a macOS LaunchAgent (default
  30 min) so import-based tools stay current. Opt-in — never auto-activated.
- **Coverage canary now probes importer tools (v3.13):** `halyard doctor`'s
  capture-coverage check was extended from the live-capture tools to
  `github-copilot` and `codex`, so a silent importer break (on-disk sessions
  newer than the last import) is flagged instead of going unnoticed.
- **VS Code Copilot OpenTelemetry capture (v3.12):** a durable, standards-based
  capture path for Copilot that does not read VS Code's internal storage (the
  thing that keeps drifting). `halyard install-vscode-otel` points VS Code's
  Copilot OTLP exporter at a local receiver Halyard runs on `127.0.0.1:4318`
  (inside the `halyard service` process, started only when you opt in);
  `uninstall-vscode-otel` reverses it. GenAI-semconv spans are mapped to
  `AiSession` rows — model, tokens, tool calls/errors, api/tool time — and
  aggregated per session. Privacy is enforced by a metadata allowlist: prompt,
  response, tool names, and file paths are never read, proven by a fuzz test.
  The v3.7 file importer stays as a fallback and is dedup-coordinated so the two
  paths never double-count a session (OTel wins). `halyard doctor` nudges when
  Copilot is on disk but OTel isn't wired up. (Phase-0 live verification is
  deferred — the build environment had no Copilot Chat install — so the mapper
  is built defensively against the documented spec; see the v3.12 design notes.)

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
