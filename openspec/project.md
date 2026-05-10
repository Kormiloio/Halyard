# Halyard — Project Context

This file is loaded by OpenSpec on every change. It establishes shared
conventions so each change proposal doesn't have to re-explain them.

## Mission

Halyard is the open AI work ledger. It captures where AI-assisted work happens
— time, tokens, models, cost, project attribution, and trust metadata — and
turns that data into proof-of-work artifacts for individuals and AI Work
Intelligence for teams.

For the solo developer, freelancer, or small AI shop: time, AI spend, project
attribution, and invoice evidence as plain text on your machine. The near-term
wedge is proving AI-assisted work without exposing prompts or source code.

For teams and enterprises: the same ledger can later support redacted sync,
governance, cost centers, and cross-tool AI Work Intelligence. That layer is
additive and gated on design-partner pull plus security readiness.

The individual experience is the entry point. The enterprise layer is
optional, additive, and built on the same open data format.

**Strategic posture (May 2026):** OSS-first, trust-first. The product is
launching to developer communities (HN, Reddit, Lobsters) before any
commercial motion. Users and community trust come before paid tiers. No
proposal should introduce paid-tier language, upsell surfaces, or
enterprise-only gates into any OSS-facing surface (CLI help, README, demo)
until the community has validated the format.

## Non-negotiables

These constraints apply to every change. Any proposal that breaks them needs
to explicitly justify the exception.

1. **Local-first.** No required cloud service. Optional paid tiers may exist
   later for sync or e-filing, but the core product runs offline against a
   local folder.
2. **Plain text forever.** All user data is stored in human-readable,
   diff-friendly text formats. Use existing public specs where they already
   exist; publish Halyard-owned specs after the local format has proven useful
   and at least one external emitter exists:
   - Time → [hledger timeclock](https://hledger.org/timeclock.html)
   - Ledger → [Beancount](https://beancount.github.io/)
   - Invoices → markdown with YAML frontmatter
   - Config → TOML
   No proprietary formats. No SQLite-as-source-of-truth.
3. **Files are the source of truth.** Any UI (CLI, web, future GUI) is a
   view onto the files. The agent edits the same files a human would.
4. **No silent writes.** Any modification to user data is proposed to the
   user with a diff and waits for approval. Read-only operations need no
   approval.
5. **No prompt or source-code capture by default.** Halyard captures metadata,
   not transcripts, prompts, file contents, or code context.
6. **Trust labels over fake certainty.** Reports distinguish captured,
   calculated, allocated, inferred, missing, and mixed data.
7. **MIT licensed.** Permissively. Forever.

## Project layout (per Halyard project)

A user's Halyard project directory contains:

```
my-business/
├── halyard.toml          # business name, currency, invoice counter
├── clients.toml          # array of clients
├── projects.toml         # array of projects (linked to client_slug)
├── time.timeclock        # hledger timeclock format (human time)
├── ai-sessions.log       # AI usage events: tokens, model, cost (added in v1)
├── ledger.beancount      # Beancount ledger (added in v2)
├── invoices/             # generated invoice .md and .pdf files
├── expenses/             # raw bank/receipt CSVs (added in v2)
├── templates/            # optional user overrides
│   └── invoice.md.j2
└── .gitignore
```

Per-user agent state lives in `~/.halyard/`, not in the project folder:

```
~/.halyard/
├── projects          # project registry — one absolute path per line (v2.18)
├── active            # active-timer state (written by start_timer, deleted by stop_timer)
├── cache.db          # SQLite read-model cache (v2.14); rebuilt from plain-text files on demand
└── halyard.log       # internal error log
```

**Project registry (`~/.halyard/projects`):** One absolute path per line. Lines
starting with `#` are comments. `halyard init` appends the new project path
idempotently. `halyard db sync` reads the registry as its primary project
discovery source; it falls back to CWD for unregistered projects. Stale paths
(directories that no longer exist or no longer contain `halyard.toml`) are
skipped with a warning and can be removed with `halyard projects forget <path>`.

**SQLite cache schema policy (v2.18):** `cache.db` carries a `PRAGMA user_version`
integer. Every schema change ships a forward-only migration in the `_MIGRATIONS`
list in `db.py`. Destructive migrations (those that cannot be expressed as
`ALTER TABLE … ADD COLUMN`) use the `REQUIRES_RESET` sentinel, which causes
`get_db()` to exit with a clear message asking the user to run
`halyard db reset && halyard db sync`. The plain-text files are never modified
by migrations; reset only deletes the cache.

`ai-sessions.log` is plain text, open format — the same local-first guarantee
as `time.timeclock`. New sessions are always appended. Since v2.17, attribution
corrections are written as `a <hash> key=value …` amendment records appended to
the log; the original `s` lines are never mutated.  The log is now genuinely
append-only in normal operation: in-place rewrites (`_rewrite_lines_atomic`)
are reserved exclusively for user-driven interactive triage
(`halyard assign-unattributed` interactive prompt).  Cloud sync and enterprise
layers must read from this local source of truth; they do not replace it.

## Active focus (May 2026)

**Current sequence — do not reorder without explicit justification:**

1. ~~**v2.18 — Cache and audit hardening** (complete)~~ — project registry,
   SQLite schema migrations, content-addressed session IDs, invoice front-matter
   rate fields, test backfill for v2.11–v2.15.
2. **OSS launch:** `pipx install halyard && halyard init` must work end-to-end
   in a clean venv. Gate: zero-friction first-use experience confirmed. Then
   HN / Reddit / Lobsters post.
   Pre-flight checklist (in order):
   - [ ] Make GitHub repo public (currently private).
   - [ ] Configure PyPI trusted publisher: PyPI project → Settings →
     Trusted Publishers → Add (Owner: Kormiloio, Repo: Halyard,
     Workflow: publish.yml, Environment: pypi).
   - [ ] Create "pypi" environment in GitHub repo Settings → Environments.
   - [ ] Push `v0.2.0` tag (already pushed; re-push or cut `v0.2.1` after
     going public to trigger the publish workflow).
   - [ ] Confirm `pipx install halyard` installs 0.2.0 from PyPI.
   - [ ] Write HN / Reddit / Lobsters post.
3. **v2.24 — Outcome metadata uplift — shipped:** branch as a first-class
   `AiSession` field, commit count at session close, code delta for all four
   collectors, `halyard outcome sync` command for PR linkage, SQLite v3 schema.
   Outcome score moves from 2/10 to 6/10. (902 tests passing.)
4. **v2.25 — Honors and achievements:** `halyard honors` CLI command + Captain's
   Quarters panel on The Bridge. Ranks (Civilian → Commodore), stripes (watch
   streaks), medals (Eight Bells, Full Sail, Clean Manifest, Lighthouse, Signal
   Master, Harbor Master, Fair Winds, Rescue at Sea). Pure read layer — no new
   data formats. Spec in `openspec/changes/v2.25-honors-and-achievements/`.
   **Status: complete (762 tests passing).**
5. **v2.26 — Passport and Friends of the Sea:** Passport stamps (one per AI
   tool first used, in Captain's Quarters) + Friends of the Sea (one sea
   creature per completed project, auto-assigned by personality trait, with
   voyage stages: Anchors Aweigh → Making Headway → Rounding the Mark →
   Flying Colors → Shipshape · Moored). New `voyages.toml` data file.
   `halyard voyage` CLI group. Spec in
   `openspec/changes/v2.26-passport-and-friends/`.
   **Status: complete (799 tests passing).**
6. **v2.27 — VS Code manual capture:** `halyard install-vscode-tasks` creates a
   workspace VS Code task that records `tool=vscode` sessions through
   `record-session`; Passport, dashboard, TUI, README, and tests understand the
   VS Code tool slug. This is manual/editor-task capture, not native Copilot
   token capture, because Copilot exposes no public session-end hook. Spec in
   `openspec/changes/v2.27-vscode-manual-capture/`.
   **Status: complete.**
7. **v2.28 — Auto human timer:** presence-window model writes `i`/`o` timeclock
   entries automatically while Claude Code is active. One timeclock block per
   contiguous work session; 30-minute inactivity gap closes and reopens. Manual
   timer (`halyard start`) always wins — auto-timer silently skips. Entries
   tagged `;auto` for auditability. State in `~/.halyard/auto-timer`. Spec in
   `openspec/changes/v2.28-auto-human-timer/`.
   **Status: complete (921 tests passing).**
8. **v2.29 — Pre-ship hardening:** seven issues identified in a pre-launch
   architecture and security review. (1) Windows crash on `fcntl` import —
   platform guard + OS classifiers + README note. (2) TOML injection in
   `voyages.py` and `git_context.py` — replaced f-string building with
   `tomli_w.dumps()`. (3) Pricing hash bypass — `update-pricing` now prompts
   or aborts on hash change; `--accept-changed` flag for CI. (4) `_session_line_hash`
   hash mismatch — `AiSession._raw_hash` carries the original line hash before
   amendment folding. (5) SQLite cache staleness — `INSERT OR IGNORE` changed to
   `INSERT OR REPLACE`. (6) Datetime timezone inconsistency — standardized to
   local-naive across all collectors. (7) OS declaration in pyproject.toml and
   README. Spec in `openspec/changes/v2.29-pre-ship-hardening/`.
   **Status: in progress.**
9. **v2.19 — Attestable AI work appendix:** signed, verifiable, client-safe
   proof of AI-assisted work. Gated on v2.24 so the appendix can include
   commit and PR evidence.

## Deferred or gated

- **v3.0 outcome graph** — connecting sessions to commits, PRs, tests, and
  deliverables — waits until at least one design partner explicitly asks for it.
  v2.24 is the incremental step; v3.0 is the full graph. Do not conflate them.
- Org admin dashboards, SSO/RBAC, and hosted enterprise reporting wait until
  security posture and design-partner pull justify them.
- Native automatic collectors (Copilot, Windsurf) wait until v2.18 hardens the
  foundation and the tools expose usable APIs/hooks. Manual VS Code/Copilot
  capture is allowed and shipped in v2.27.
- Calendar scheduling is strategic candy; defer.
- The public `ai-sessions.log` spec is published only after at least one
  external tool emits the format. Writing the spec before adoption exists is
  vanity work.

## Stack defaults

- **Language:** Python 3.11+
- **CLI:** Typer + Rich
- **Models:** Pydantic v2
- **Templating:** Jinja2
- **PDF:** typst (subprocess)
- **Time parsing:** dateparser
- **Agent:** Anthropic SDK with tool use (single-turn loop in v0)
- **Tests:** pytest with golden-file tests for renders
- **Lint/format:** ruff

Any deviation from this stack needs justification in the change's `design.md`.

## How changes work

Each change lives at `openspec/changes/<change-slug>/` with:

- `proposal.md` — why & what's changing (high level)
- `specs/*.md` — requirements with scenarios, in WHEN/THEN form
- `design.md` — technical approach, choices, trade-offs
- `tasks.md` — the implementation checklist

Completed changes get archived to `openspec/changes/archive/YYYY-MM-DD-<slug>/`.

## Spec-first rule

**Write the spec before writing the code.**

For any non-trivial change (new command, new collector, new concept):

1. Create the change directory and write `proposal.md` first.
2. Get alignment on the proposal before writing `design.md` and `specs/`.
3. Only then open code. `tasks.md` is the bridge — write it before starting
   implementation, check items off as you go.

What counts as non-trivial: anything that adds a new user-facing command,
introduces a new file or data format, changes existing behaviour in a
way that affects stored data, or requires design decisions with trade-offs.

Bug fixes, test additions, and internal refactors that don't change the
observable contract are exempt — do those directly.

The purpose of spec-first is not process for its own sake. It's to ensure
the "why" is captured while it's fresh, so future contributors (and future
AI assistants) can understand intent, not just implementation.
