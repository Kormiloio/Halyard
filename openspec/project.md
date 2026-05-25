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
(`halyard adopt` command).  Cloud sync and enterprise
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
   - [ ] Push `v0.2.1` tag after going public to trigger the publish workflow.
   - [ ] Confirm `pipx install halyard` installs 0.2.1 from PyPI.
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
   **Status: complete (931 tests passing).**
9. **v2.30 — Tool visibility:** `by_tool_usage: list[ToolUsageBucket]` added to
   `AiReport`. CLI `halyard report` gains "By tool" section. Dashboard tools
   panel replaced with session-count bars and token column. Usage analytics panel
   uncapped (was limited to 4 tools) and gains token counts. Zero-cost tools
   (Codex free tier) now appear in all surfaces. Spec in
   `openspec/changes/v2.30-tool-visibility/`.
   **Status: complete (918 tests passing).**
10. **v2.31 — Install-hook hardening:** `_do_install_hook_claude()` cross-file
    dedup prevents double-recording when hooks exist in both local and global
    Claude Code settings. Setup wizard prompts for global vs project scope.
    `halyard doctor` gains `hook.claude.duplicate` warning check. Spec in
    `openspec/changes/v2.31-install-hook-hardening/`.
    **Status: complete (918 tests passing).**
11. **v2.32 — VS Code extension and metadata parity:** VS Code extension
    (`vscode-extension/`) tracks active editing time via workspace events,
    captures branch and code delta via git, and records sessions through
    `halyard record-session --tool vscode`. Status bar shows elapsed time;
    recovery prompt on restart for unfinished sessions. All four collectors
    upgraded to emit interaction metadata fields (`interaction_count`,
    `user_message_count`, `assistant_message_count`, `prompt_count`) using the
    "unavailable is not zero" rule. `record-session` gains 20+ metadata flags.
    Spec in `openspec/changes/v2.32-vscode-extension-metadata-parity/`.
    **Status: complete (952 tests passing).**

    **Refactor (post-v2.32):** `cli.py` split from 3,352 lines into 12 focused
    modules using a `register(app: typer.Typer) -> None` pattern. Six sub-app
    modules (`cli_service`, `cli_config`, `cli_db`, `cli_projects`, `cli_voyage`,
    `cli_outcome`) use `app.add_typer()`; six register-pattern modules
    (`cli_hooks`, `cli_setup`, `cli_session`, `cli_importers`, `cli_report`,
    `cli_org`) use `register(app)`. `cli.py` is now ~160 lines: app definition,
    default callback, register calls, easter eggs. No observable behaviour change;
    mypy clean on 71 source files, 952 tests passing.

12. **v2.33 — Hub-first dashboard + voyage auto-detection:** `halyard dashboard`
    defaults to hub scope when a hub is configured. Voyage stage auto-inferred
    from all-time session history (`_infer_voyage_stage`): At anchor → Anchors
    Aweigh → Making Headway → Rounding the Mark → Flying Colors — no
    `voyages.toml` required. `DashboardState` gains `all_sessions` to avoid
    double-reads. Timeclock missing → "neutral" health (not "error") bug fixed.
    Spec in `openspec/changes/v2.33-hub-first-dashboard/`.
    **Status: complete (952 tests passing).**

13. **v2.34 — Presence-aware human timer:** `_compute_presence_today()` merges
    today's AI session windows (30-min gap) into a presence estimate stored on
    `HumanTimeReport.presence_minutes`. Human Time card shows "auto-detected"
    time when no manual timer was started — "0m today" no longer the default
    for active users. No writes to `time.timeclock`; computed on read.
    Spec in `openspec/changes/v2.34-presence-timer/`.
    **Status: complete (952 tests passing).**

14. **v2.35 — Subscription cost allocation:** AI Cost card shows
    `~$X.XX · allocated from plans` when captured API cost is $0.00 and
    `ai-plans.toml` defines a plan, using the existing ledger total. Trust label
    distinguishes captured vs allocated cost. No new data formats.
    Spec in `openspec/changes/v2.35-subscription-cost/`.
    **Status: complete (952 tests passing).**

15. **v2.36 — Proof score transparency:** Voyage panel proof score now shows
    `attr X% · tokens Y%` component breakdown inline so users understand a
    score of 40% with zero attribution. Fix prompt "run halyard adopt" shown
    when attribution < 100%. Sessions column adds all-time sub-label.
    Spec in `openspec/changes/v2.36-proof-score-transparency/`.
    **Status: complete (952 tests passing).**

16. **v2.37 — Smart attribution:** `halyard.toml` walk-up inference (CWD → root)
    makes project detection work for monorepos, non-git directories, and any
    user's layout without central config. `halyard adopt` promotes an
    auto-tracked directory to a named project in one command. `AiSession.remote`
    captures the normalized git remote at session time so unattributed sessions
    can be grouped by repo in `halyard doctor` and the dashboard Overview tab.
    Privacy-first: non-git directories stay anonymous; no local paths stored.
    Spec in `openspec/changes/v2.37-smart-attribution/`.
    **Status: complete (974 tests passing).**

17. **v2.38 — Review hardening:** full-codebase review remediation. Cost
    math moved to `Decimal`/`ROUND_HALF_UP`; a single `usage.sum_spend`
    convention so `halyard budget` and invoicing reconcile; pricing
    cache/multipliers invalidate together and never silently fall back;
    Rich-markup injection closed across all TUI panes; `adopt`/Gemini
    glob/auto-timer inputs validated; SQLite migrations self-heal; the
    `state_integrity` mode cache is per-project and the sidecar write is
    crash-atomic; PR-attribution datetimes normalized to UTC; TUI memory
    bounded; Codex import streams + prunes dedup state. H7 (move TUI
    aggregation off the event loop) and four LOW dedup items are deferred
    with rationale. Spec in `openspec/changes/v2.38-review-hardening/`.
    **Status: complete (987 tests passing).**

18. **v2.39 — Input injection hardening:** independent security review
    findings the posture-level pass missed. TOML injection via a cloned
    repo's `git config user.name` in `halyard init` closed (sanitize +
    parse round-trip); untrusted Stop-hook `transcript_path` validated
    (allowlisted root, no symlink, regular file, 25 MB cap, streamed
    read); Gemini history reads size-bounded; `rate_history_from_git`
    tolerates malformed commit diffs. Spec in
    `openspec/changes/v2.39-input-injection/`.
    **Status: complete (995 tests passing).**

19. **v2.40 — Authenticated state integrity:** adds
    `state_integrity = "hmac"` — keyed HMAC-SHA256 sidecars (`.hmac`)
    using a per-user 0600 secret at `~/.halyard/integrity.key`, fail-closed
    if the key is missing. Closes the CRITICAL review finding that the
    unkeyed `hash` sidecar is trivially forgeable. Equally important: the
    docstring, `docs/trust-model.md`, and `halyard doctor` now state the
    guarantee **honestly** — `hash` is corruption-detection only (not
    tamper-resistant), `hmac` resists processes that can't read the key
    but not a full local-account compromise. No more overclaiming. Spec
    in `openspec/changes/v2.40-authenticated-state/`.
    **Status: complete (1003 tests passing).**

20. **v2.41 — Trust hardening:** residual security-review items. Pricing
    fetch origin-pinned (final URL must be `https://raw.githubusercontent.com`
    or the body is rejected before parsing); `_halyard_exe()` resolves via
    `which` first and only trusts `argv[0]` under a venv/site/system
    prefix (no writable-dir wrapper persisted into tool configs);
    dashboard token compared in constant time; `cli_hooks` refuses to
    overwrite an existing-but-unparseable user config (raises the
    actionable `HookWriteError` instead of clobbering); `docs/trust-model.md`
    now documents the dashboard-local-only posture and every user config
    file Halyard writes. Spec in
    `openspec/changes/v2.41-trust-hardening/`.
    **Status: complete (1014 tests passing).**

21. **v2.42 — Customizable dashboard layout:** every panel and metric
    carries a stable `data-panel` id; a client-side script (no server
    surface) injects per-panel drag handles + collapse toggles, restores
    saved order and collapsed set from `localStorage` on every load
    (including the 10s auto-refresh), constrains drag to within a
    container, and a topbar "reset layout" control returns to default.
    Fail-safe: a script error leaves the server-rendered dashboard fully
    visible. Controls sit top-right of every box; a topbar collapse/expand-all
    master control toggles every box. Browser-verified. Spec in
    `openspec/changes/v2.42-dashboard-layout/`.
    **Status: complete (1020 tests passing).**

22. **v2.43 — Actionable health warnings:** the topbar status pill is
    now a focusable button with a hover `title` summarizing health;
    clicking it opens a server-rendered popup listing every non-healthy
    check (status + detail) and pointing to `halyard doctor` for full
    diagnostics/fixes (the dashboard `HealthCheck` has no per-check fix
    field — that lives on the CLI's `DoctorCheck`; nothing is
    fabricated). Dismiss via close button / Esc / outside-click;
    fail-safe script, no server surface. Browser-verified. Spec in
    `openspec/changes/v2.43-health-detail/`.
    **Status: complete (1023 tests passing).**

23. **v2.44 — TUI health visibility:** parity with the v2.43 web health
    surface on the terminal side. The TUI status bar shows a compact
    `⚠ N — press h` chip when any `build_health_checks` result is
    warning/error (nothing when healthy); a new `HealthModal` (`h` key)
    lists each failing check's label/status/detail plus a `halyard
    doctor` pointer. Reuses the authoritative health data — no new data
    file, no persistence, no command; check-derived text is escaped
    (v2.38 invariant). Spec in
    `openspec/changes/v2.44-tui-health/`.
    **Status: complete (1029 tests passing).**

24. **v2.45 — Cursor/Gemini hook install de-dup:** the cursor/gemini
    installers matched "already present" by exact command string, so
    every distinct halyard binary path stacked another hook entry
    (observed: 4 cursor + 2 gemini stale registrations → duplicate
    placeholder sessions). Now keyed off arg0 basename like Claude's
    installer: each event keeps exactly one halyard hook for the current
    binary, stale/dead-path entries are healed, foreign hooks preserved,
    and a no-op leaves the file byte-unchanged. Spec in
    `openspec/changes/v2.45-hook-dedup/`.
    **Status: complete (1034 tests passing).**

25. **v2.46 — Suppress evidence-free collector sessions:** the Gemini
    AfterAgent and Cursor stop handlers appended an `s` session on every
    fire, even when nothing happened (no tokens, no history, no tool
    calls, no interactions, no code delta, no model). The shared
    Cursor `beforeSubmitPrompt`/`stop` chain and spurious Gemini fires
    therefore wrote zero-signal ledger rows. New shared
    `collectors.session_has_evidence` predicate: a stop fire with no
    evidence of a real turn is skipped (state still reset); any single
    signal (tokens/history/tool/interaction/code/commit/real model)
    still records as before. Honest scope: constant synthetic token
    values come from external hook payloads, not a Halyard default —
    this only removes the wholly-empty fire Halyard controls. Spec in
    `openspec/changes/v2.46-evidence-free-sessions/`.
    **Status: complete (1053 tests passing).**

26. **v2.47 — Evidence-free guard for Claude Code:** v2.46's
    `session_has_evidence` predicate extended to
    `claude_code.handle_stop_hook` (v2.46 had explicitly scoped Claude
    Code out pending evidence — now shown). A Stop fire that resolved no
    transcript/tokens and has no model/interactions/tools/code (the
    `claude-unknown 0 0 $0` stub that dominated "Recent AI Sessions") is
    no longer written; transcript-enriched real sessions are unaffected.
    Two existing collector tests updated from the old stub contract.
    Spec in `openspec/changes/v2.47-claude-code-evidence/`.
    **Status: complete (1053 tests passing).**

27. **v2.48 — Dashboard data correctness:** `halyard dashboard` with no
    `--project-dir` now aggregates the de-duplicated union of every
    registered project log (registry ∩ existing) + hub instead of
    showing only the (junk) hub — the default view is total real work
    (`build_ai_report` gained an optional `sessions=` arg to enable
    this; header reads `All Projects · N`). Collectors reject
    implausible hook sessions (>12h span — the frozen-`2026-05-07`
    synthetic Cursor rows). `registry.register_project` refuses temp-dir
    paths and a conftest fixture isolates the registry so the test
    suite can never pollute `~/.halyard/projects` again. Operational:
    pruned 711 temp registry paths + re-cleaned the hub log (backups
    kept). Spec in `openspec/changes/v2.48-dashboard-data-correctness/`.
    **Status: complete (1059 tests passing).**

28. **v2.49 — Cursor/Gemini stop requires a recorded session start:**
    an external daemon (thedotmack claude-mem `worker-service.cjs`) was
    firing the Cursor `stop` / Gemini `AfterAgent` hooks with canned
    `2000/400` & `100/50` payloads — plausible duration + nonzero tokens,
    so v2.46/v2.48 guards couldn't catch them. The tell: no
    `cursor-session`/`gc-session` state file (the start phase never
    ran). `handle_stop_hook` now returns early if `cursor-session` is
    absent; `handle_agent_stop` returns early if `_read_state()` is
    None. Real two-phase lifecycles always record a start first, so no
    real session is lost; stop-only synthetic fires produce nothing.
    Claude Code unaffected. Spec in
    `openspec/changes/v2.49-require-session-start/`.
    **Status: complete (1062 tests passing).**

29. **v2.50 — Read-only MCP server:** `halyard mcp` (stdio) exposes the
    aggregate ledger to MCP clients (Claude Code / Cursor) so the agent
    that *generates* the work can query it in-context. Six read-only
    tools — `work_summary` (flagship rollup), `sessions`,
    `spend_in_range`, `project_breakdown`, `cost_by_model`,
    `outcomes_status` — over the v2.48 aggregate data layer. No
    mutations, no daemon (client spawns per session), metadata only (no
    prompts/code/transcripts). `mcp` SDK is an optional extra
    (`pip install 'halyard[mcp]'`); the command lazy-imports and prints
    an actionable message if absent — core install unchanged. Ships a
    repo-root `.mcp.json` for one-step registration. Spec in
    `openspec/changes/v2.50-mcp-server/`.
    **Status: complete (1068 tests passing).**

30. **v2.51 — MCP auto-registration:** `halyard init` / `halyard setup`
    now auto-registers the v2.50 read-only MCP server with every MCP
    client detected on PATH (Claude Code → `~/.claude.json`, Cursor →
    `~/.cursor/mcp.json`, Gemini CLI → `~/.gemini/settings.json`), so
    end users never hand-edit a config file. Reuses the hook-install
    machinery: PATH-gated, best-effort `OSError` in the auto path,
    no-clobber via `_load_existing_settings`, byte-stable no-op via
    `_settings_unchanged`, foreign servers (e.g. `claude-mem`)
    preserved — only the single `mcpServers.halyard` key is touched.
    Explicit `halyard install-mcp-claude|cursor|gemini` mirror the
    `install-hook-*` set. Spec in
    `openspec/changes/v2.51-mcp-autoregister/`.
    **Status: complete (1077 tests passing).**

31. **v2.52 — Unwired-tool detection nudge:** `halyard doctor` flags a
    supported AI tool that is installed but has zero Halyard
    integration — live-hook tools on PATH with neither hooks nor the
    MCP server, and Codex with on-disk history but nothing imported —
    emitting a `warn` (never `error`, exit-code contract preserved)
    with the exact one-line fix. Read-only, on-demand, no daemon;
    flows through the existing `DoctorReport` so dashboard/TUI health
    surfaces inherit it. Spec in
    `openspec/changes/v2.52-tool-detection-nudge/`.
    **Status: complete (1088 tests passing).**

32. **v2.53 — Parse-time synthetic-telemetry guard:** the v2.45–v2.49
    guards lived in the hook collectors, but the contaminating writer
    (thedotmack claude-mem `worker-service.cjs`) appends canned rows to
    `ai-sessions.log` directly, bypassing every write guard. v2.53
    moves the defence to the read chokepoint:
    `collectors.session_is_synthetic_telemetry` recognises the exact
    canned fingerprint (`(2000,400,"claude-3.5-sonnet")` /
    `(100,50,"gemini-2.0-pro")` with `cost==0` and no project — a
    combination genuine current work cannot produce) and
    `ai_log.parse_sessions` excludes those rows, so no surface (CLI,
    dashboard, aggregate, MCP) ever sees them. Raw lines stay in the
    log (immutable, auditable; no quarantine write — parse runs per
    render). Also `or`-ed into the three collector write guards
    (defence in depth). Spec in
    `openspec/changes/v2.53-synthetic-read-guard/`.
    **Status: complete (1096 tests passing).**

33. **v2.54 — Future-dated sessions are impossible:** a session whose
    start is in the future cannot have happened; such rows sorted to
    the top of every newest-first view. Root cause was `seed-demo`
    itself: it anchored demo sessions to `month_start + day_offset`,
    so running it mid-month produced future-dated rows in the real
    ledger. Fix: `seed-demo` anchors the timeline to ~yesterday
    backwards (never future, regardless of run date); new
    `collectors.session_starts_in_future` (5-min skew grace) folded
    into `session_is_implausible` (write-path defence) and applied at
    the `parse_sessions` read chokepoint (narrow — future only, so
    long-but-real history is never retroactively hidden). Raw lines
    stay in the log (read-only exclusion, like v2.53). Bug-class fix
    (spec-exempt); 5 tests in `tests/test_v254_future_session_guard.py`.
    **Status: complete (1112 tests passing).**

34. **v2.55 — Review hardening (DbError + hash-collision guard):** two
    code-review findings. (a) `db.py` raised `SystemExit` from
    library-level code for a needs-reset cache — uncatchable by
    programmatic/test consumers; now raises a catchable
    `DbError(RuntimeError)`, mapped to a clean message + exit 1 at a
    new `cli.main()` entry seam (`[project.scripts]` →
    `halyard.cli:main`). (b) `session_hash` 48-bit truncation is the
    `s`↔`a` join key (can't be widened without orphaning existing
    amendments); documented the bound and added a `parse_sessions`
    guard that quarantines a genuine prefix collision (same hash,
    different raw line) instead of silently mis-folding an amendment.
    Bug-class/internal (spec-exempt); 5 tests in
    `tests/test_v255_dberror_and_hash_collision.py`.
    **Status: complete (1117 tests passing).**

35. **v2.56 — External-review hardening batch (6 findings):**
    - **P1-a** tz-aware ISO log rows crashed `parse_sessions` (v2.54
      regression: aware `start` vs naive `now`). Normalised at the
      parse boundary + guard coerces aware input.
    - **P1-b** a partially-applied multi-statement migration could be
      marked complete (`executescript` aborts at the first re-hit
      ALTER, remaining ALTERs skipped, `user_version` still bumped).
      New `_apply_migration` applies each statement idempotently so a
      partial migration self-heals.
    - **P1-c** active-timer state bypassed `read_trusted_state` — v2.40
      tamper detection never applied to `~/.halyard/active`; writes
      passed no mode so no sidecar was written. Now writes resolve the
      owning project's mode and reads verify + fail closed; a present
      sidecar (`detect_sidecar_mode`) blocks the downgrade-via-tampered
      -path hole.
    - **P2** shared `halyard.slug` validator (was: only checked for a
      `/`) enforced in `halyard start` + dashboard `/api/start`;
      `_amendment_line` runs values through `_safe_field`.
    - **P2** vscode `halyard.executable` wrapper commands
      (`uv run halyard`) now work via `splitExecutable`.
    - **P2** vscode vitest scoped to `src/**/*.test.ts` (compiled
      `out/` no longer breaks `npm test`).
    Bug-class/internal (spec-exempt); commits 27b8690, 09752bb,
    c042089. **Status: complete (1142 Python tests + 19 vscode).**

36. **v2.59 — Collector schema-drift canary:** collectors parse the
    *internal* formats of Claude Code / Cursor / Gemini / Codex; an
    upstream format change silently degrades capture to unreal-model
    sessions (no crash — "unavailable is not zero"). `halyard doctor`
    now flags, per tool, a *sustained* regression: the last
    `_DRIFT_WINDOW` (5) sessions all have an unreal model while an
    older session for that tool had a real one (healthy baseline →
    this is a regression, not a never-worked tool). `warning` not
    `error` (capture works, enrichment degraded — exit-code contract
    preserved); detection only (never reads upstream formats); flows
    through `DoctorReport` so dashboard/TUI inherit it. Per-tool
    isolated. Spec in
    `openspec/changes/v2.59-collector-drift-canary/`; 8 tests.
    **Status: complete (1150 tests passing).**

37. **v2.60 — Claude Code collector enrichment:** the primary tool is
    the weakest collector — populate `session_id`, `tool_calls/errors`,
    `wall_seconds`, `user_message_count`, `model_breakdown` from the
    Stop payload/transcript (unavailable-is-`None`, no schema change).
    Spec in `openspec/changes/v2.60-claude-code-enrichment/`.
    **Status: complete (1156 tests passing).**

38. **v2.61 — Multi-model session attribution:** one session uses many
    models (router/main/subagent); cost + per-model rollups currently
    misattribute to one `model`. Generalise `model_breakdown` to
    per-model usage; cost = Σ per-model; shared `iter_model_usage`
    seam. Spec in `openspec/changes/v2.61-multimodel-attribution/`.
    **Status: complete (1168 tests passing).**

39. **v2.62 — Cache-aware cost correctness:** audited per-collector
    input/cache token semantics. **Finding: no live double-count** —
    claude_code/cursor get Anthropic-schema input (natively exclusive
    of cache); gemini_cli/codex_app already subtract the cached subset
    at capture. Rescoped from a bug fix to regression-proofing: shared
    `normalise_input` seam codifies the fresh-input invariant (no-op
    for the exclusive collectors, behaviour-identical for the gross
    ones), 8 lock-in tests incl. double-count regression + no-op
    proof, PRD "Token contract" subsection. `cache_write` is
    structurally unavailable for Gemini/Codex (no cache-creation
    field) → documented `None`, not dropped; history immutable, not
    retro-corrected. Spec in
    `openspec/changes/v2.62-cache-cost-correctness/`.
    **Status: complete (1198 tests passing).**

40. **v2.63 — Session time decomposition:** **DEFERRED 2026-05-16**
    after a Phase 0 audit. Unbuildable as specced: (1)
    `agent_active_seconds` is already a stored/serialized field
    (work_health + record-session CLI) — "derive it, never store"
    would be a breaking change; (2) Gemini exposes no api/tool split
    to any collector by default — the `/quit` summary is terminal
    -only, on-disk session JSON has timestamps but no durations, and
    structured api/tool latency exists solely via opt-in
    OpenTelemetry. Deferred until a collector can see the split; the
    OTEL path is split out as **v2.67**. Codex `tool_seconds` alone
    isn't worth a schema bump. Audit in
    `openspec/changes/v2.63-session-time-decomposition/design.md`.

41. **v2.64 — Stats & graphs parity surface (commodity only):** match
    the table-stakes stats single-tool dashboards show (heatmap,
    per-model time series, streaks, messages, peak hour) on existing
    `UsageAnalytics` data — the "parity floor" so the moat lands.
    Rescoped: this is the *commodity* half only; the moat-shaped
    graphs are **v2.66**, which **ranks above this**. Additive; moat
    panels stay primary. Phase 0 audit found the data layer already
    rich (`UsageAnalytics.daily` exists → `daily_activity` dropped;
    only `total_messages` + per-day-per-model `model_io` added). The
    prior Models chart used a window-wide *approximation*; v2.64
    replaces it with the real per-day-per-model in/out split.
    Owner-approved carve-out: full TUI widget parity (not just
    information parity) despite the TUI-deferral policy. Spec in
    `openspec/changes/v2.64-stats-graphs-parity/`.
    **Status: complete (1206 tests passing).**

42. **v2.65 — Attribution integrity & visibility:** the under-protected
    moat half. `attr_method` collapses the inference chain into `git`
    and attribution has no confidence label (cost has trust labels;
    attribution has none). Records the real rung (`repo-map`/`toml`/
    `git-auto`), derives an `attribution_confidence`
    (timer>mapped>toml>auto>none) surfaced in CLI/dashboard/MCP like
    cost trust, adds a `doctor` attribution-quality canary (adrift-rate
    + per-remote regression, v2.59 pattern, `warning`-only), and emits
    exact per-remote `link-repo`/`adopt` remediation (propose, never
    write). Back-compat (legacy `git`→`auto`); no cost-path change.
    Spec in `openspec/changes/v2.65-attribution-integrity-visibility/`.
    **Status: complete (1185 tests passing).**

43. **v2.66 — Moat visualization surface:** the *moat* counterpart to
    v2.64's commodity parity — graphs no single-tool dashboard can
    draw because none have a project/client/$/outcome:
    **cost-by-client over time**, **attribution-confidence trend**
    (v2.65 data visualized), **per-project billable-evidence cards**
    (human time + AI cost + outcomes + confidence), and a **leakage
    funnel** (adrift $ per remote + its one-command fix). Existing
    data only; server-rendered SVG, no JS; moat panels render *above*
    the v2.64 commodity stats (executable ordering invariant). Ranks
    **above v2.64**. Spec in
    `openspec/changes/v2.66-moat-visualization/`.
    **Status: complete (1192 tests passing).** $ accuracy inherits
    v2.62 when it lands. TUI per-project column deferred (tracked).

44. **v2.67 — Gemini OpenTelemetry ingestion:** the split-out of
    v2.63's deferred api/tool-time goal via its only real source —
    Gemini CLI's opt-in OTLP outfile (`gemini_cli.api_response` /
    `gemini_cli.tool_call` measured `duration_ms`, joined by
    `session.id`). Lands v2.63's `api_seconds`/`tool_seconds` as
    **independent optional fields** (NOT the breaking
    `agent_active_seconds`-as-property conversion v2.63 specced —
    that field stays stored). Opt-in only (`install-gemini-telemetry`
    diff-and-approve; `doctor` nudge), capture-only privacy,
    bounded fail-closed read. Spec in
    `openspec/changes/v2.67-gemini-otel-ingestion/`. Phase 0 verified
    against the installed gemini-cli 0.41.1 (bundle source + bundled
    docs, no API quota spent): `outfile` supported; file framing is
    **concatenated pretty-printed JSON** (not line-delimited) and
    `session.id` is a **resource** attribute — both corrected from the
    original assumption and recorded in design.md; gate = proceed.
    **Status: complete (1240 tests passing).**

45. **v2.19 — Attestable AI work appendix:** **MOVED OUT OF OSS SCOPE
   2026-05-14 → [Kormiloio/Halyard-Enterprise](https://github.com/Kormiloio/Halyard-Enterprise).**
   A signed, verifiable, client-safe proof artifact is a *bottoms-up
   enterprise* feature: its value rises with cross-party use (a
   recipient verifying a signed appendix), so it does not fit
   single-user OSS scope. The OSS repo already ships the solo-user
   slice — local trust-labelled invoice evidence + v3.0 invoice
   -appendix PR refs (unsigned). Signing/verification/cross-party
   trust lives in the enterprise repo. See `docs/current-direction.md`
   §15. **Not an OSS changeset — do not implement here.** The
   OSS-safe solo-user slice is split out as **v2.68**.

46. **v2.68 — Local AI-work evidence appendix (OSS slice of v2.19):**
   the single-user half that legitimately stays in OSS. Audit found
   `render_ai_evidence_appendix` already exists but is invoice
   -embedded only with no integrity marker. Adds a standalone
   `halyard evidence` command (reuses the renderer verbatim) + a
   deterministic `sha256:` self-digest that is tamper-**evident**
   (author can publish/re-hash) but explicitly **not** signing or
   authorship proof — that stays enterprise (v2.19). Honest-boundary
   statement in the artifact; no overclaim (v2.40 discipline).
   `evidence.py` + `halyard evidence` (`--all/--project/--client/
   --month`, stdout default, `--out`/`--force`, `--verify`); renderer
   reused verbatim; digest excludes the footer + wall-clock so it is
   reproducible. Spec in
   `openspec/changes/v2.68-local-evidence-appendix/`.
   **Status: complete (1217 tests passing).**

47. **v2.69 — Machine-readable JSON output:** unify + complete the
   `--json` surface. Audit found it already exists inconsistently
   (doctor/health/usage/log/outcome, 3 shapes); flagship `report`,
   `budget`, `status` have none. Adds a shared `jsonio` seam,
   migrates the existing ones onto it (keys preserved), adds
   `report/budget/status/evidence --json`, documents an additive
   -only contract. `evidence --json` carries no digest (the v2.68
   digest covers markdown only). `jsonio` seam (datetime→ISO,
   Path→str, `_`-fields skipped); `usage` migrated + `health` routed
   through it; doctor/log/outcome left on their existing valid JSON
   emitters (documented deviation — migration was churn/risk, no
   user gain). Spec in `openspec/changes/v2.69-json-output/`.
   **Status: complete (1223 tests passing).**

48. **v2.70 — TUI ↔ web dashboard parity:** the owner-decided lift of
   the TUI-deferral policy. TUI is a generation behind: no moat pane
   (cost-by-client, attribution-confidence, leakage, billable
   evidence) and no leverage pane. Adds both as text-mode panes
   reusing `moat.py`/`attribution.py`/report builders; factors the
   inline leverage math into a shared `leverage.summarize` consumed
   by both web + TUI (single source of truth). Testable-text layer
   only (v2.64 `UsagePane` pattern; no Pilot harness). Spec in
   `openspec/changes/v2.70-tui-dashboard-parity/`.
   **Status: complete (1230 tests passing).**

49. **v2.71 — Pre-OSS review hardening:** a full multi-pass review
   (collectors/hooks, core data model, TUI/dashboard, DB/CLI) ahead
   of the OSS release. Fixes verified defects: an absolute hook crash
   backstop (`_run_hook` — a collector exception can no longer
   traceback into the host tool) + tolerant payload int coercion;
   two v2.38 markup-escaping regressions (`usage_pane`,
   `branch_modal`); `tags` round-trip corruption on a comma (now
   percent-encoded, legacy comma form still reads); `append_session`
   no longer full-re-parses the log per append (O(n²)→O(n) bulk
   import; milestone easter eggs moved to `maybe_emit_milestones`);
   SQLite `busy_timeout`+WAL; uniform `--json` `{"error":…}` contract
   with diagnostics to stderr; incremental `a `-record tailing in the
   TUI store; consistent bounded-read hardening (codex/gemini_history
   symlink+size); `install-hook-claude` byte-stable no-op; Decimal
   ledger accumulation; `last_sync()` read-only-safe; dependency
   upper bounds. Folded-in risk list: typst invoked by resolved
   `which()` path (residual $PATH risk accepted — same model as
   git/open); timeclock structural anomalies (`timeclock_anomalies`
   + `_timeclock_check` warning) so silent under-billing on
   malformed i/o pairs becomes a visible nudge. Documented (not
   built): amendment-record trust gap; unknown-kv preservation;
   concurrent-timeclock reconstruction (hledger is sequential —
   detection not guessing). Spec in
   `openspec/changes/v2.71-review-hardening/`.
   **Status: complete (1260 tests passing).**

50. **v2.72 — Declarative field registry (stability/refactor):**
   `ai_log.py` defines 45+ optional `AiSession` fields. Previously,
   their wire handling was duplicated in `to_log_line` (manual `if`
   checks) and `_parse_line_result` (manual `match` arms). v2.72
   introduces a single `_FIELDS` registry; both writer and parser
   iterate it, ensuring byte-for-byte symmetry and eliminating the
   writer/parser drift bug class. Positional fields are unchanged.
   **Status: complete (1306 tests passing).** Spec in
   `openspec/changes/v2.72-field-registry/`.

51. **v2.73 — Sortable dashboard tables (UX):** every web table is
   server-rendered with a single fixed sort. Add progressive-
   enhancement client-side column sort (~8 tables) — clickable
   headers, numeric/time/severity/text comparators, blanks-last,
   asc→desc→clear. Load-bearing requirement: sort state persists in
   `sessionStorage` and re-applies across the 10 s `<meta refresh>`
   (a naive sort resets every 10 s). No backend/data/format change;
   no-JS baseline = today's fixed sort. Health sorts by severity
   rank, never glyph text; Note/Fix not sortable; a column whose key
   can't be made unambiguous is dropped, not shipped wrong. Cosmetic,
   not launch-blocking. Spec in
   `openspec/changes/v2.73-table-sort/`. Shipped: `_stbl` table
   tagging (`data-cols` per-column kinds) across ~11 tables,
   `_table_sort_script` (sessionStorage-persisted across the 10 s
   refresh), `data-sort-val`/`data-sev` on ambiguous cells, no-JS
   baseline unchanged. Budget panel dropped from the set (card-based,
   not a table) — recorded, not shipped wrong. Headers made operable
   at runtime (deviation from server-`<button>`, lower regression
   risk; recorded).
   **Status: complete (1266 tests passing).**

52. **v2.74 — Ambient status (competitive-read of CodexBar):** adopt
   the *surface* lesson (the highest-leverage view is the one never
   opened) without its job. One status contract from existing
   builders (capture health + spend + adrift + budget burn/
   projection — zero new captured data), a cross-platform
   `status --watch`, and an optional Phase-0-gated macOS menu-bar
   shim via the existing `halyard service`. Hard non-goals enforced
   as tasks: no provider quota/reset tracking, no provider-breadth
   race, no incident polling, never reads provider
   credentials/cookies/keychains. Projection is a labeled estimate;
   single-source parity with `report`/`budget`/`doctor`. PRD/ARD in
   `docs/PRD-ambient-status.md` / `docs/ARD-ambient-status.md`; spec
   in `openspec/changes/v2.74-ambient-status/`.
   **Status: complete (1286 tests passing).** `status_snapshot.py`
   composed only from existing builders (zero new captured data);
   `status --snapshot`/`--watch` shipped, v2.69 `status --json`
   timer contract preserved; projection is a labeled estimate
   (no divide-by-zero); privacy test pins no provider-credential
   access. macOS menu-bar shim deferred (Phase-0 gate — needs a real
   launchd/PyObjC environment; contract + terminal watch ship now).

53. **v2.75 — Extensible log contract (unknown-token preservation):**
   dual-justified — closes the v2.71 documented silent-drop gap AND
   is the concrete forward-compat enabler so consumers (incl. the
   additive Halyard-Enterprise layer) extend the line format without
   forking the OSS parser. Adds `AiSession.extra` passthrough: parser
   `case _:` preserves unknown `key=value` verbatim, `to_log_line`
   re-emits it sorted/injection-safe; byte-stable for the empty case;
   identity (`_session_id`/`session_hash`) and quarantine/amendment
   paths unaffected; OSS never *interprets* `extra`. Ships with a
   docs pass: `docs/integration-contract.md` (stable, additively
   versioned log + `--json` surface) and neutral `payer:work-unit`
   attribution wording. Spec in
   `openspec/changes/v2.75-extensible-log-contract/`.
   **Status: complete (1275 tests passing).** `AiSession.extra`
   passthrough shipped: parser `case _:` preserves unknown tokens
   (key-shape guarded, no shadowing), `to_log_line` re-emits sorted/
   injection-safe; byte-stable empty case; `_session_id` identity
   unaffected; OSS never interprets `extra`. Decision gate cleared
   (byte-stable achieved; no parse-and-warn fallback needed).

54. **v3.0 — Outcome graph (sessions → commits/PRs/tests):** the
   strategic anchor — ties each AI session to engineering artifacts so
   Halyard can answer "is the AI spend producing engineering leverage?"
   Shipped incrementally rather than as one drop: amendment keys +
   `AiSession` outcome fields (v2.24), `outcomes`/`pr_cache` schema
   (v2.18 migration framework), git/gh signal collectors
   (`halyard.outcomes`, `git_context`, `shell_history`,
   `attempt_tracker`), `halyard outcome sync/report/attribute`, the
   Leverage panel (web + TUI parity, v2.70), invoice PR-ref appendix,
   and the privacy-contract fuzz test. Tasks §1–§6 complete; §7
   (design-partner dark-mode run + write-up) is a user/GTM gate, not
   code — the changeset ships green without it.
   **Status: code-complete (1286 tests passing); gated only on
   design-partner validation (§7), not on code.** Spec in
   `openspec/changes/v3.0-outcome-graph/`; full PRD in
   `strategy/prd-outcome-graph.md`. No standalone `design.md` was
   written: the design was realized through the incremental changesets
   above, each carrying its own design notes. The first engineering
   increment on top of v3.0 shipped as v3.1 (roadmap entry 55).

55. **v3.1 — Review-friction signals (cycle-time + review burden):**
   the highest-leverage of the three v3.0-deferred workstreams — turns
   "did it ship?" into "what did shipping cost?", the metric that makes
   Halyard an AI-ROI record, not just an activity record. An
   enrichment pass layered on v3.0's resolved `pr_ref` (never
   re-resolves): per unique PR, `review_comments`, `review_rounds`,
   `time_to_merge_s`, `review_decision`, all trust `captured`. A
   gated Phase-0 spike invalidated the design's one-call assumption
   before any code (`gh pr view --json comments` is issue-only; inline
   review comments need a second `gh api .../pulls/<n>/comments` call)
   — so the shipped shape is ≤2 gh calls per unique PR, merged PRs
   cached permanently (friction immutable post-merge), open/closed on
   TTL, total-failure not cached. Privacy is the binding constraint:
   counts/enum/timestamps only, the `--json` field list carries no
   body/title/author, fuzz-tested across every surface. Surfaces:
   `outcome report` per-bucket medians, web + TUI Leverage parity line
   (shared `leverage.summarize`), invoice appendix friction cell — each
   byte-identical to v3.0 when no friction data exists. Additive SQLite
   migration (v4→v5), four optional `AiSession` fields + `a` amendment
   keys (v2.75 extensible-token path unaffected).
   **Status: complete (1315 tests passing; +30 over v3.0, ≥25
   required).** Spec in `openspec/changes/v3.1-review-friction/` with
   recorded Phase-0 findings. The sibling v3.0-deferred workstreams
   (tool errors / approval rejections; MCP-server inventory) remain
   unspecced — each needs collector-side work, not GitHub data, and
   gets its own changeset when prioritized. (One pre-existing,
   unrelated, order-dependent failure — `test_adrift_regression_fires`
   — fails identically with v3.1 stashed; tracked separately, not a
   v3.1 regression.)

56. **v3.2 — Struggle signals (surface-only):** completes the leverage
   triad — v3.0 "did it ship?", v3.1 "what did review cost?", v3.2
   "how much did it thrash to get there?" — with **zero new data
   collection**. A collector-coverage audit found `tool_errors`/
   `tool_calls` already captured by all four collectors and
   `accepted/rejected_suggestion_count` captured by Cursor only, so
   this is purely surfacing already-parsed fields. Shared
   `summarize_struggle` (web+TUI parity, same mechanism as v3.1) +
   per-bucket `OutcomeBucket.struggle`. The load-bearing rule is
   honest asymmetric-capture labelling: rejections are gated on the
   pre-existing `interaction_data_available` field and rendered via a
   single `render_rejection_phrase` that is **never a bare 0** —
   either a count with explicit coverage ("over N of M sessions; rest:
   not captured") or "not captured". No schema, no log token, no
   collector diff, invoice appendix untouched (internal signal).
   **Status: complete (1333 tests passing; +17, ≥15 required).** Spec
   in `openspec/changes/v3.2-struggle-signals/`. This shipped the
   v3.1-shaped slice of the deferred "tool errors / approval
   rejections" workstream (the part where the substrate already
   existed). Still unspecced by design: **cross-collector rejection
   capture** (claude_code/gemini_cli/codex_app emitting rejections —
   the real collector work) and **MCP-server inventory** (greenfield,
   no field/capture path) — each its own future changeset.

57. **v3.4 — MCP-server usage inventory (privacy-first):** adds the
   *capability* axis to the leverage story — which MCP servers a
   session actually used — at **zero new sensitive-data egress**. A
   Phase-0 spike found the signal already in Claude Code's parse loop:
   `tool_use` blocks are iterated for v3.2's count, and an MCP tool is
   named `mcp__<server>__<tool>`, so the server segment is one read
   away. The load-bearing piece is the privacy model (new
   `mcp_inventory.py`), modelled on the `shell_history` allowlist:
   **integer count always; server names only if on a fixed public
   in-repo allowlist; a non-allowlisted server is counted but never
   named/logged/egressed; the raw `mcp__*` string, tool segment, and
   args are never retained.** Scoped to *usage* (derived) — *MCP
   availability* (reading config files = commands/URLs/env) is
   explicitly deferred. Additive migration v5→v6; two optional
   `AiSession` fields + log tokens (v2.75 path byte-stable). Shared
   `summarize_mcp`/`render_mcp_phrase` → web + TUI parity line ("MCP: N
   servers (github, filesystem +2)"), absent → v3.2-identical; report
   & invoice untouched. Phase-0 found Cursor/Gemini have no per-tool
   names (honest absence, R5) and Codex unconfirmed (deferred), so
   v3.4 ships **Claude-Code-only** — the designed partial rollout. One
   recorded deviation: the R7 capture-time opt-out gate was dropped to
   match the v3.1/v3.2 pattern (the unconditional allowlist reduction
   *is* the privacy boundary), rather than add an inconsistent bespoke
   gate.
   **Status: complete (1352 tests passing; +19, ≥15 required).** Spec
   in `openspec/changes/v3.4-mcp-inventory/`. **v3.0-deferred trio
   status:** review-friction shipped (v3.1); struggle shipped (v3.2);
   MCP *usage* shipped (v3.4); cross-collector rejection shipped
   (v3.3 — detected for Claude Code and Codex, Gemini N/A); still
   open — MCP *availability* (deferred, config-reading privacy surface).

58. **v3.5 — Claude Code client-surface tag (CLI vs. desktop):** the
   Claude Code collector tags every session `tool="claude-code"`
   regardless of which launcher the user actually invoked — terminal
   CLI, desktop app, or IDE extension all collapse into one bucket.
   For an owner who uses two surfaces daily, the dashboard cannot
   answer "which surface do I lean on for what kind of work?" v3.5
   adds an optional advisory `client_surface` sub-tag
   (`cli`/`desktop`/`ide`/`unknown`) on `AiSession`, detected from the
   hook process's own environment (env vars + parent-process
   ancestry). `tool="claude-code"` is unchanged; the tag is purely
   additive and rendered with honest "(heuristic)" labelling.
   **Status: complete (1298 tests passing).** Spec in
   `openspec/changes/v3.5-claude-code-surface/`.

59. **v3.3 — Cross-collector rejection capture (UX):** struggle
   signals (v3.2) surfaced rejections but only Cursor *captured*
   them. v3.3 closes the gap for Claude Code (detected from
   transcript error markers) and Codex Desktop (detected from
   rollout log statuses). These are counted as a subset of
   `tool_errors` for these tools, labeled with honest "(overlaps
   tool_errors)" metadata. Gemini CLI is confirmed N/A due to
   lack of approval markers.
   **Status: complete (1366 tests passing).** Spec in
   `openspec/changes/v3.3-cross-collector-rejection/`.

60. **v3.6 — Windsurf native collector (onboarding):** Windsurf
   (Codeium) IDE produces agentic Cascade sessions. v3.6 adds an
   autonomous collector (`src/halyard/collectors/windsurf.py`) that
   hooks into Windsurf's `hooks.json` to capture session timing
   and interaction counts. Uses `trajectory_id` as the session key
   and a TTL-based finalization strategy (30-min inactivity).
   **Status: complete (1374 tests passing).** Spec in
   `openspec/changes/v3.6-windsurf-collector/`.

61. **v3.7 — GitHub Copilot Importer (automated capture):**
   v3.7 introduces a native importer for the VS Code GitHub
   Copilot extension. Discovered internal VS Code workspace
   storage JSONL logs enable retroactive metadata capture
   (timestamps, output tokens, user/assistant counts, tool
   calls) and outcome tracking (files touched manifest).
   Brings Copilot out of manual-task mode.
   **Status: complete (1377 tests passing).** Spec in
   `openspec/changes/v3.7-copilot-importer/`.

62. **v3.8 — Gemini CLI `.jsonl` rollout capture (bugfix):** the Gemini
   collector silently stopped recording — the last Gemini ledger row was
   2026-05-07. Gemini CLI changed its on-disk history from a single-object
   `session-*.json` checkpoint to a line-delimited `session-*.jsonl` rollout
   (one header line, then one event per line, `$set` patches for
   `lastUpdated`). `gemini_history.py` only understood `.json`, and three
   guards rejected the new files (glob misses `.jsonl`; the 25 MB whole-file
   cap vs. an 825 MB rollout; whole-file `json.loads` on a non-document).
   Both the importer and the live hook route through `gemini_history`, so the
   parser fix repairs both. `parse_session_file` now dispatches on suffix and
   streams `.jsonl` line-by-line (memory bounded by the longest line; per-line
   + total-byte caps; the hook passes a tight budget and falls back to the
   `gc-session` accumulator on huge files). The load-bearing correctness
   detail: the rollout **re-emits the same `gemini` message many times** as it
   streams (one id seen 53×), so events are **deduped by `id`** (final
   emission wins) — summing every emission inflated tokens ~30×. After dedup,
   per-model totals match Gemini's own `/quit` report (pro-preview exact;
   flash-preview within ~3%, the residual being API sub-requests the rollout
   folds into one message id). Discovery globs (`find_all_session_files`,
   `find_session_file`, `import-gemini`) now include `.jsonl`. The legacy
   `.json` path is byte-for-byte unchanged. Session `9d3f7d6b-…` (825 MB)
   backfilled into the ledger. **Second defect fixed in the same pass (the
   live-hook half of the outage):** `handle_agent_stop` parsed the now
   tz-aware `gc-session` `turn_start` (trailing `Z`) with
   `datetime.fromisoformat` and subtracted naive `datetime.now()`, raising
   `TypeError` that the hook crash-backstop swallowed — so every `AfterAgent`
   fire silently recorded nothing and never reset state (`AfterModel` survived
   because it does no datetime math). Same tz-aware/naive class as v2.56 P1-a;
   `start` is now normalised to local-naive (v2.29 convention) with a
   regression test. Spec in `openspec/changes/v3.8-gemini-jsonl-rollout/`.
   **Status: complete (1399 tests passing; +22).**

63. **v3.9 — Claude Code Stop-hook catch-up (silent under-capture):** a
   ground-truth audit (ledger vs. transcript) found the *primary* tool
   capturing only ~35% of output tokens — a completed session had 33 turns
   but 15 rows, with a ~6-hour stretch of work and zero rows. Root cause:
   capture needs `UserPromptSubmit`+`Stop` in lockstep, with the turn start in
   a single `cc-session` file cleared on every `Stop`; a missed `Stop` (common
   in the desktop app) dropped those turns with no recovery. Fix:
   `handle_stop_hook` anchors the transcript read to a high-water mark
   (`_last_recorded_end` — the latest recorded end for the session) instead of
   this turn's start, so one `Stop` after a gap back-fills everything since the
   last row. Windows stay contiguous (no double-count); first turn unchanged.
   Spec in `openspec/changes/v3.9-claude-code-catchup/`.
   **Status: complete (+2 tests).**

64. **v3.10 — doctor capture-coverage canary:** the systemic gap that hid both
   outages — `doctor` only checked "hooks installed", and the v2.59 drift
   canary keys on recent *rows* so a tool with *no* rows is invisible. New
   `_capture_coverage_checks` compares each live-capture tool's newest on-disk
   session file against its last captured row; if the tool keeps writing
   sessions while the ledger stalls, capture broke. Probes `claude-code` +
   `gemini-cli`; baseline-gated (no false-positive on never-used tools);
   `_COVERAGE_LAG_DAYS = 2` grace; `warning`-only; flows through
   `DoctorReport`. Would have flagged Gemini in ~2 days instead of 16. Spec in
   `openspec/changes/v3.10-coverage-canary/`.
   **Status: complete (+4 tests).**

65. **v3.11 — `import-all` + scheduled importer:** import-based collectors
   (Codex/Copilot/Gemini) only reach the ledger when an importer runs. New
   `halyard import-all` runs all three idempotently (Gemini body extracted to
   `run_gemini_import`); `halyard install-import-timer`/`uninstall-import-timer`
   schedule it via a macOS LaunchAgent (`import_timer.py`, default 30 min).
   Opt-in (autonomous writer — never auto-activated); first run bulk-imports
   on-disk history (a few 2026-05-07 Gemini hook rows would double-count, so a
   clean reconcile should precede enabling). Also under this investigation: the
   Halyard VS Code extension was fixed to use an absolute `halyard.executable`
   (the bare `"halyard"` default isn't on a Finder-launched VS Code's PATH).
   Spec in `openspec/changes/v3.11-scheduled-import/`.
   **Status: complete (1407 tests passing; +2).**

66. **v3.12 — VS Code OpenTelemetry collector (Copilot capture):** the durable
   replacement for scraping VS Code's internal storage, which keeps drifting
   (v3.13). VS Code 1.119+ emits standard OpenTelemetry (GenAI semconv) to a
   configurable local OTLP endpoint (`github.copilot.chat.otel.*`, off by
   default). Shipped: a pure span→`AiSession` mapper (`collectors/vscode_otel.py`)
   over the documented GenAI semconv + OTLP/JSON encoding (metadata-only
   allowlist — content attributes, tool names, file paths never read);
   per-`session.id` aggregation; a localhost OTLP/HTTP+JSON receiver
   (`collectors/otel_receiver.py`) on `127.0.0.1:4318`, started from
   `run_dashboard` **only when opted in** (`~/.halyard/vscode-otel.enabled`),
   idle-TTL + shutdown flush (Windsurf v3.6 pattern); `install-vscode-otel` /
   `uninstall-vscode-otel`; importer dedup-coordinated (OTel wins; fast-path
   state file + authoritative ledger `job_id` scan); `doctor` nudge when Copilot
   is on disk but OTel unwired. Out of scope: the Azure/Grafana ops dashboard
   (their lane; the ledger is ours). **Phase-0 deferred:** the Copilot Chat
   extension isn't installed in the build env, so no live OTLP payload was
   captured — the mapper is built defensively against the documented spec and
   probes both resource/span `session.id` placements; live verification is a
   fixture diff, not a rewrite (see design.md "Phase 0 (deferred)").
   **Status: code-complete (1432 tests passing; +19), gated on live re-verify.**
   Spec in `openspec/changes/v3.12-vscode-otel-collector/`.

67. **v3.13 — Copilot session format-drift fix + importer coverage canary:** a
   live test caught `import-copilot` capturing nothing — VS Code changed the
   chat-session file to an incremental patch log (`kind:0` snapshot +
   `kind:1/2` key-path updates), and the output now arrives via
   `["requests", N, "response"]` sub-path patches the old parser never applied,
   so every recent session skipped as "empty" (same drift class as Gemini).
   `parse_chat_session` now reconstructs the final state from the patches.
   The v3.10 coverage canary is extended to `github-copilot`/`codex` (it had
   only probed live-capture tools, so it missed this). Capture restored; v3.12
   is the durable fix. Spec in `openspec/changes/v3.13-copilot-format-drift/`.
   **Status: complete.**

68. **v3.14 — Gemini session de-duplication:** a live Gemini session
   (`70615981-…`) was counted ~2.5× over (3 ledger rows: 147,186/2,990/365,090
   vs the `/quit` 59,970/1,451/170,196). Root cause: the Gemini history file is
   the *whole-session* record, and both capture paths read all of it — the live
   hook re-parses it every `AfterAgent` fire and writes the running **cumulative**
   total as that turn's row (so an N-turn session sums overlapping snapshots),
   and the importer appends one more whole-session row that `_dedup_sessions`
   misses (different `start`, no `project`). Fix: a read-time
   `collapse_gemini_sessions` in `parse_sessions` (the one choke point all 20
   counting surfaces share) keeps a single canonical row per Gemini session id
   — resolved from `session_id=` (hook) or `job_id=gemini:<id>` (importer), so
   already-written rows collapse too — picking the most-complete row (max
   input+output), tie-broken toward the attributed/wider-window row. Also applied
   in the aggregate merge for the cross-log case. Read-time only; raw lines stay
   in the log (v2.53/v2.54 philosophy), so it retroactively corrects the polluted
   ledger without a rewrite. Honest limitation: the secondary `gemini-3.1-flash-lite`
   utility/router model is **not in the history source** (only `/quit`/OTel have
   it), so it stays uncaptured — documented in `docs/collector-coverage.md`, not
   fabricated. Spec in `openspec/changes/v3.14-gemini-session-dedup/`.
   **Status: complete (1439 tests passing; +7).**

69. **v3.15 — Coverage canary for Cursor and Windsurf:** the capture-coverage
   canary (v3.10/v3.13) — the safety net that turns a *silent* capture break into
   a visible `halyard doctor` warning — only watched 4 of 7 tools; Cursor and
   Windsurf were blind spots (same silent-failure class as the Gemini outage, for
   the two tools it didn't cover). They have no enumerable per-session files
   (Cursor → `state.vscdb` SQLite; Windsurf → `~/.codeium/windsurf` store), and
   parsing those would re-introduce the fragile vendor-format scraping v3.12 was
   built to escape. So the canary is extended using **coarse storage mtimes only**
   (Cursor `…/User/**/state.vscdb`; Windsurf `cascade/`), never reading contents,
   with a wider grace (`_COVERAGE_LAG_DAYS_COARSE = 4`, vs 2 for the file-precise
   tools) and a best-effort, honestly-worded warning that names the uncertainty.
   Baseline-gated, `warning`-only, flows through `DoctorReport`. Verified on the
   real machine: Cursor (storage older than its last capture) correctly produces
   no warning — "unused, not broken," not a false alarm. Honest limit: coarse, not
   a precise per-session reconciliation. Spec in
   `openspec/changes/v3.15-cursor-windsurf-coverage/`.
   **Status: complete (1445 tests passing; +6).**

70. **v4.0 — Halyard Hub Architecture:** Transition to a Daemon-Broker model
    to eliminate I/O latency in tools and enable cross-platform service
    management (Linux/Windows). Primary ingestion via local OTLP/HTTP.
    Spec in `openspec/changes/v4.0-halyard-hub/`.
    **Status: complete (full suite green: 1483 tests passing).**

71. **v4.1 — Polyglot Proof & Public Spec:** Stabilize the `/v1/ingest` API and
    publish the `ai-sessions.log` data format specification. Invite community
    emitters. Spec in `openspec/changes/v4.1-polyglot-proof/`.
    **Status: complete (full suite green: 1483 tests passing).**
72. **v4.2 — Hub-Managed Active State:** Consolidate `~/.halyard/active` and
    timer logic into Hub memory to eliminate filesystem polling latency and
    fragmentation. Spec in `openspec/changes/v4.2-hub-managed-state/`.
    **Status: complete (full suite green: 1483 tests passing).**
73. **v4.3 — Real-Time Dashboard:** Enable push-based UI updates using SSE from
    the Hub. Sessions appear in the Bridge dashboard instantly.
    Spec in `openspec/changes/v4.3-realtime-dashboard/`.
    **Status: complete (full suite green: 1483 tests passing).**
74. **v5.0 — Duplicate-Effort Detection:** Identify when multiple AI sessions
    overlap on the same branch or task using git metadata. Provide real-time
    collision alerts in CLI and Dashboard.
    Spec in `openspec/changes/v5.0-duplicate-effort/`.
    **Status: complete — engine, CLI warning, and dashboard Collisions panel all
    shipped and test-covered (1483 tests passing). A richer per-session Gantt
    visualization is deferred (see design §4).**

75. **v5.1 — Dashboard trio row:** Group the Outcomes, Wake, and Capture panels
    into a single three-up row at the Outcomes position; tighten the Wake
    heatmap and fix leverage-panel overflow at third-width. Presentational
    only — no data, format, or CLI changes.
    Spec in `openspec/changes/v5.1-dashboard-trio-row/`.
    **Status: complete (1483 tests passing).**

76. **v5.2 — Codex importer re-imports in-progress sessions:** The importer
    skipped any rollout UUID seen once, freezing sessions captured mid-write at
    a partial snapshot. Now it re-imports when the rollout file has grown
    (size-fingerprinted dedup state) and collapses the redundant rows at read
    time by session UUID — mirroring the Gemini collapse.
    Spec in `openspec/changes/v5.2-codex-growth-reimport/`.
    **Status: complete (1488 tests passing).**

77. **v5.3 — Concurrency + observability hardening:** the three verified items
    from an architecture review (the other two ship as v5.4). (1) **Reader
    shared lock** — `read_locked_file()` (`LOCK_SH`) closes a torn-read window
    where a reader concurrent with a large in-progress append could see a
    partial line; `parse_sessions`/`unattributed_log_count` read through it.
    Honest scope: the ledger is append-only and `_write_quarantine` only copies
    to `quarantine.log`, so this is robustness, not the data-loss the review
    claimed. (2) **Diagnostic log** — `log_diagnostic()` records silent
    fallbacks (Hub timeout, every git subprocess failure) to
    `~/.halyard/diagnostic.log` so degradation is observable. (3) **Latency
    test** — a real `HubServer` slower than the 150 ms client timeout proves the
    degrade-to-local-write path. Rejected: raising the (deliberate fail-fast)
    timeout; a FastAPI rewrite. Spec in
    `openspec/changes/v5.3-concurrency-observability/`.
    **Status: complete (1495 tests passing).**

78. **v5.4 — Dashboard page shell → Jinja2 + timezone ADR:** first increment of
    breaking up the ~3,355-line `dashboard.py` monolith flagged in an
    architecture review. The page chrome (doctype/head/topbar/metrics/grid
    wrapper/footer/scripts) and per-panel scaffolding move from the
    `_render_state` f-string into `src/halyard/templates/dashboard.html.j2`
    (cached `autoescape=True` env); panel builders are untouched and their
    pre-escaped HTML flows through as `|safe`, so output is behaviour-preserving
    (100 existing dashboard tests pass unchanged; +3 templating tests). Also
    lands the missing `docs/adr/` with `0001-timezone-model.md` — records the
    accepted naive-local-domain / UTC-machine-log split, its single coercion
    boundary (`_to_naive_local`), and the additive `tz=`-token path gated on
    Halyard-Enterprise. Rejected: FastAPI port (unjustified for a localhost
    single-user bridge); UTC-everywhere (breaking format migration, no
    single-user benefit). Spec in
    `openspec/changes/v5.4-dashboard-templating/`. The sibling concurrency/
    observability review items (reader read-locking, fallback `diagnostic.log`,
    Hub latency test) shipped as v5.3.
    **Status: complete (1495 tests passing).**

79. **v5.5 — Hub worker resilience + bounded OTel accumulator:** the two
    verified items from a security review of the Hub's OTLP ingestion (the
    review's per-field schema validator, pricing-signing, and token-access-log
    recommendations were assessed and rejected — log-injection is already
    prevented at the `to_log_line` write boundary, pricing already uses
    HTTPS + origin-pin + SHA-256 TOFU, and the `0600` token is read directly by
    a local attacker rather than via the function). (1) **Worker-tick
    isolation** — `_worker_loop` split into a scheduler + `_worker_tick`
    wrapped in `try/except` + a `log_diagnostic` breadcrumb, so one malformed
    session can no longer silently kill the daemon worker and halt all
    background writes. (2) **Bounded accumulator** — `_MAX_OTEL_SESSIONS` cap +
    `_evict_excess_otel()` (oldest-by-`last_update`) so a local client spamming
    distinct `session.id`s can't grow `_otel_acc` without bound. Spec in
    `openspec/changes/v5.5-hub-worker-resilience/`.
    **Status: complete (1498 tests passing).**

80. **v5.6 — Dashboard: panel templates, external CSS, native partial refresh:**
    three refinements to the server-rendered Bridge (architecture kept — the
    right fit for a local-first `pipx` tool; FastAPI/React rewrite rejected).
    (#2) `_CSS` (437 lines) → `templates/dashboard.css` via cached `_load_css()`,
    output unchanged. (#1) the 7 repetitive table builders (models/tools/
    projects/collisions/time/adrift/sessions) now render through a `data_table`
    macro in `templates/panels/_macros.html.j2`; logic-heavy panels stay in
    Python by design. (#3) the full-page `<meta refresh>` is replaced by a
    zero-dependency native partial refresh — a 10s timer + Hub SSE swap the
    `#metrics`/`#grid` regions in place and re-run sort + a new idempotent
    `HalyardApplyLayout` hook, so sort/order/collapse survive and scroll/focus
    are preserved. **HTMX was evaluated and rejected** (vendoring needs the file
    offline; a CDN breaks offline-first). Browser-verified (no reload, in-place
    swap, collapse survives). Spec in
    `openspec/changes/v5.6-dashboard-templating-refresh/`.
    **Status: complete (1498 tests passing).**

81. **v5.7 — Dashboard "B+": tabbed overview + richer charts + panel on/off:**
    owner-picked redesign after prototyping three directions
    (`prototypes/dashboard_redesign.py`). Adds a calm **Overview** tab built
    from hero inline-SVG visuals (cost donut [cost-only], model-mix donut,
    tokens trend, activity heatmap, top-projects, outcomes, KPI strip) and a
    **tab bar** (Overview/Money/Sessions/Voyage/Health/All). Tabs are
    **client-side show/hide** — every panel stays in the DOM (real renderers,
    all creature/passport/medal/rank icons intact), so existing tests + the
    v5.6 partial-refresh keep working; only visibility changes (re-applied via
    `HalyardApplyTabs`). Restores the controls: **per-panel on/off** (✕ + a
    `▦ panels` manage menu, persisted) alongside collapse/drag, and the v2.73
    column **sort** `⇅` (already present — a duplicate glyph was caught in
    browser verification and removed). **Attribution normalized** for the
    charts (`kormilo/halyard` + `git/Halyard` + `kormilo:halyard` → one);
    full remote→slug map is a follow-up. New inline-SVG chart helpers
    (`_svg_donut`/`_svg_area`/`_svg_stacked_bar`) — no JS charting dep,
    offline-first. Browser-verified end-to-end. Spec in
    `openspec/changes/v5.7-dashboard-b-plus/`.
    **Status: complete (1505 tests passing).**

## Deferred or gated

- **v3.0 outcome graph** — code-complete (see roadmap entry 54). The only
  outstanding item is the §7 design-partner validation run + public
  write-up, which is a GTM gate, not engineering work. v2.24 was the
  incremental step; v3.0 is the full graph — do not conflate them.
- Org admin dashboards, SSO/RBAC, and hosted enterprise reporting wait until
  security posture and design-partner pull justify them.
- Native automatic collectors (Copilot, Windsurf) wait until v2.18 hardens the
  foundation and the tools expose usable APIs/hooks. Manual VS Code/Copilot
  capture is allowed and shipped in v2.27.
- Calendar scheduling is strategic candy; defer.
- TUI widget/app coverage (`tui/app.py`, `tui/widgets/*`) is a
  conscious deferral: the state layer `tui/store.py` is 100% covered
  (it shapes what panes render and is the only correctness-bearing
  TUI code), but exercising the Textual widgets needs the
  `Pilot`/`run_test()` harness — high effort, low return while the
  TUI is a secondary surface behind the CLI and web dashboard.
  Revisit only if the TUI becomes first-class. **Carve-out (v2.64,
  owner-approved 2026-05-16):** the `UsagePane` stats parity content
  is exercised directly (it renders to `last_rendered_text`, no Pilot
  harness needed) because the parity surface is the strategic
  first-impression; this is a deliberate, scoped exception, not a
  reversal of the broader deferral. **Lift (v2.70, owner decision
  2026-05-16):** the carve-out is generalised — the TUI must be on
  par with the web dashboard, so the new moat + leverage parity panes
  also render to `last_rendered_text` and are unit-tested directly.
  The Pilot-harness deferral still stands for the untouched legacy
  widgets; this lifts it only for the parity panes whose correctness
  lives in their rendered text.
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
