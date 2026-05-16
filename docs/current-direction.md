# Current Direction

This is the public orientation doc for Halyard's current product direction.
Older PRDs remain in `docs/` as historical design records, but this page and
the active OpenSpec changes are the best guide to what Halyard is trying to
become now.

---

## The Product

Halyard is the open AI work ledger.

For individuals and small AI shops, Halyard helps prove AI-assisted work:
what happened, what tools were used, what it cost, which project it belonged
to, and what can be safely shown to a client without exposing prompts or code.

For teams and enterprises, the same ledger becomes AI Work Intelligence:
cross-tool visibility, trust-labeled cost allocation, governance, and later
effectiveness signals. Enterprise aggregation is additive. It must not break
the local-first source of truth.

---

## Why OSS First

Halyard is MIT-licensed and will stay that way. The near-term goal is not
revenue — it is trust.

An individual developer installs Halyard because they want it, not because a
manager told them to. That install happens when the developer finds it on HN,
Reddit, or Lobsters and trusts that it is open, local, and honest. Trust comes
from the community validating the format before any commercial motion exists.

The sequence is: **trust → users → community → then paid.**

No paid-tier language appears in the README, the CLI help text, or any
community-facing surface until the community has validated that Halyard is a
real thing. Paid tiers exist in the strategy docs. They do not exist for the
person installing Halyard for the first time.

---

## The Wedge

The near-term wedge is proof of work for AI-assisted engineering.

The local product must be useful before any team or enterprise layer exists:

- capture AI sessions across tools automatically;
- keep logs local, plain text, and inspectable;
- track human time and AI spend by project;
- explain measured versus estimated cost with trust labels;
- generate invoice-safe evidence;
- help users clean up unattributed sessions;
- never capture prompts or source code by default.

The next network-effect feature is the attestable AI work appendix: a signed,
verifiable, privacy-preserving artifact that an individual can attach to an
invoice, deliverable, or review packet. It lands after the outcome metadata
uplift, which provides the commit and PR signals that make the appendix
meaningful.

---

## Outcome-Aware Metadata — Shipped (v2.24)

The session model now scores 6/10 on outcome awareness. Current state:

| Signal | Status |
|---|---|
| Branch name | First-class `AiSession.branch` field — all four collectors |
| `code_added` / `code_removed` | First-class fields — all collectors with git access |
| Commit count in session window | `AiSession.commit_count` — all four collectors |
| PR linkage / PR outcome | `pr_ref` + `pr_state` via `halyard outcome sync` |
| Repeated attempts on same ticket | Not captured (v3.0 scope) |

What shipped in v2.24:

1. **Branch as first-class field** — `branch: str | None` on `AiSession`,
   serialized to log and parsed back. Legacy `branch:<name>` tags auto-promoted.
2. **Commit count at session close** — `commits_in_window()` in `git_context.py`;
   called by all four collectors at stop.
3. **Code delta for Claude/Cursor** — `git diff --numstat` from `sha_at_start`
   captured at session open. Codex is pull-based so sha_at_start is omitted;
   Gemini uses its own history file (unchanged).
4. **PR linkage** — `halyard outcome sync` queries `gh pr list`, writes
   `a <hash> pr_ref=... pr_state=...` amendment records. `outcomes` and
   `pr_cache` SQLite tables added in schema v3. 1-hour cache TTL.
5. **Outcome report** — `halyard outcome report` and `halyard report --outcomes`
   bucket sessions by state: shipped (merged), in-flight (open), abandoned
   (closed), no PR, not synced.

Spec: `openspec/changes/archive/2026-05-09-v2.24-outcome-metadata/`. 902 tests passing.

---

## Agent Access (MCP) — Shipped (v2.50–v2.52)

The thesis is "AI Work Intelligence," but the ledger was only reachable
through human surfaces — the agent that *generates* the work could not
ask about it. This closes that gap, OSS-scoped and read-only.

| Capability | Status |
|---|---|
| `halyard mcp` read-only MCP server (stdio), 6 tools | v2.50 |
| Auto-registration into detected MCP clients on init/setup | v2.51 |
| `halyard doctor` warns on installed-but-unwired tools | v2.52 |

- **v2.50** — `work_summary`, `sessions`, `spend_in_range`,
  `project_breakdown`, `cost_by_model`, `outcomes_status` over the
  aggregate data layer. No mutation, no daemon (client spawns per
  session), metadata only — never prompts/code/transcripts. `mcp` SDK
  is an optional extra; core install unchanged.
- **v2.51** — `halyard init` / `setup` write `mcpServers.halyard` into
  `~/.claude.json`, `~/.cursor/mcp.json`, `~/.gemini/settings.json`,
  idempotently, preserving foreign servers. End users never edit JSON.
- **v2.52** — `halyard doctor` flags a supported tool that is
  installed but has neither hooks nor MCP, and Codex history not yet
  imported. On-demand, flows through the existing health report.

Followed by a data-trust hardening run (v2.53–v2.59): a parse-time
synthetic-row guard, future-dated-session rejection + `seed-demo` fix,
`DbError` instead of `SystemExit`, a `session_hash` collision guard,
migration self-heal, active-timer integrity coverage, shared slug
validation, and a collector schema-drift canary (`halyard doctor`
warns when a tool's capture regresses to unreal models — detection of
silent upstream-format breakage). Specs: `openspec/changes/v2.50-…`
through `v2.59-…` plus roadmap items in `openspec/project.md`.

---

## Current Build Sequence

1. **v2.18** — Cache and audit hardening: project registry, schema migrations,
   content-addressed session IDs, invoice front-matter rate fields, test
   backfill for v2.11–v2.15.
2. **OSS launch** — HN / Reddit / Lobsters. Gate: `pipx install halyard &&
   halyard init` works end-to-end in a clean venv. Goal: real users, not
   stars.
3. **v2.24** — Outcome metadata uplift — **shipped**: branch field, commit
   count, code delta for all collectors, PR linkage via `halyard outcome sync`.
4. **v2.28** — Auto human timer — **shipped**: presence-window model writes
   `i`/`o` timeclock entries automatically while Claude Code is active.
   30-minute inactivity gap closes and reopens a session. Manual timer always
   wins. Entries tagged `;auto` for auditability. (921 tests passing.)
5. **v2.29** — Pre-ship hardening — **shipped**: seven issues from a
   pre-launch architecture and security review. Windows platform safety
   (fcntl guard), TOML injection fixed (tomli_w), pricing hash bypass
   closed (PricingHashChangedError), session hash mismatch fixed
   (AiSession._raw_hash), SQLite cache stale on amendments fixed
   (INSERT OR REPLACE + parse_sessions), datetime timezone normalization
   (all collectors now emit local-naive), OS declaration in pyproject.toml
   and README. 931 tests passing.
6. **v2.30** — Tool visibility — **shipped**: `by_tool_usage` added to
   `AiReport`; CLI `halyard report` gains "By tool" section; dashboard tools
   panel uses session-count bars with token column; usage analytics panel
   uncapped. Zero-cost tools (Codex free tier) now appear everywhere. 918 tests.
7. **v2.31** — Install-hook hardening — **shipped**: cross-file dedup in
   `install-hook` prevents double-recording; setup wizard prompts for scope;
   `halyard doctor` warns on duplicate hooks in local + global settings. 918 tests.
8. **v2.32** — VS Code extension and metadata parity — **shipped**: VS Code
   extension tracks editing time, branch, and code delta; status bar timer;
   recovery prompt on restart. All four collectors upgraded to emit interaction
   metadata with "unavailable is not zero" semantics. `record-session` gains
   20+ metadata flags. 952 tests passing.
9. **cli.py refactor** — **shipped**: monolithic 3,352-line `cli.py` split into
   12 focused modules (`cli_hooks`, `cli_setup`, `cli_session`, `cli_importers`,
   `cli_report`, `cli_org`, plus six Phase 1 sub-apps). `cli.py` reduced to
   ~160 lines. No behaviour change; mypy clean on 71 source files, 952 tests.
10. **v2.33** — Hub-first dashboard + voyage auto-detection — **shipped**:
    dashboard defaults to hub scope; voyage stage inferred automatically from
    session history (no voyages.toml required); timeclock missing no longer
    shows "Error". 952 tests.
11. **v2.34** — Presence-aware human timer — **shipped**: merges today's AI
    session windows into a presence estimate; "0m today" replaced with
    auto-detected time for active users. No writes to timeclock. 952 tests.
12. **v2.35** — Subscription cost allocation — **shipped**: AI Cost card shows
    allocated plan cost when captured cost is $0.00 and ai-plans.toml is
    configured. Trust label distinguishes captured vs allocated. 952 tests.
13. **v2.36** — Proof score transparency — **shipped**: voyage panel shows
    `attr X% · tokens Y%` breakdown; fix prompt inline when attribution < 100%;
    sessions column adds all-time sub-label. 952 tests.
14. **v3.0** — Outcome graph — **shipped (24 of 27 tasks, 3 user-only).**
    Connect sessions to git commits/branches, PR refs and merge state,
    test runs (opt-in shell-history scan), and repeated-attempt branch
    heuristic. Surfaces: dashboard Leverage panel, TUI outcome glyph,
    invoice-appendix PR refs. Behind `[outcomes].enabled` opt-out and
    `[outcomes].shell_history` opt-in. 1052 tests. Design-partner recruit
    and write-up remain user tasks.
15. **v2.19** — Attestable AI work appendix — **moved to
    [Kormiloio/Halyard-Enterprise](https://github.com/Kormiloio/Halyard-Enterprise).**
    Identified on 2026-05-14 as a bottoms-up enterprise feature whose
    value rises with cross-party use (recipient verifying a signed
    appendix). Does not fit single-user OSS scope.
16. **v3+ org and enterprise** — Lives in
    [Kormiloio/Halyard-Enterprise](https://github.com/Kormiloio/Halyard-Enterprise)
    (`halyard_enterprise` package). The seven OSS modules currently
    mirrored there (`org.py`, `org_store.py`, `org_rollups.py`,
    `org_reports.py`, `cost_centers.py`, `sync.py`, `cli_org.py`) are
    frozen in OSS — see CONTRIBUTING.md.
17. **v2.50–v2.59** — Agent access + ledger-trust hardening —
    **shipped**: read-only `halyard mcp` server, MCP auto-registration,
    `doctor` unwired-tool nudge, then a data-correctness run (synthetic
    /future-row read guards, seed-demo fix, DbError, hash-collision
    guard, migration self-heal, active-timer integrity, slug
    validation, collector schema-drift canary). See the "Agent Access
    (MCP)" section above and `openspec/project.md` items 29–36.
    1150 tests + 19 vscode.

---

## What Is Deferred

These ideas are important, but not the current wedge:

- hosted dashboards;
- SSO / RBAC;
- org admin dashboards;
- (v3.0 outcome graph: shipped in OSS Halyard, see roadmap above);
- duplicate-effort detection;
- calendar scheduling for AI work;
- new collectors (Copilot, Windsurf) before v2.18;
- the public `ai-sessions.log` spec before at least one external emitter.

They should be built when user pull or design-partner evidence justifies them.

---

## Governing Principles

- Local-first by default.
- Plain text as the durable source of truth.
- No prompt or source-code capture by default.
- Trust labels instead of fake certainty.
- OSS community trust before paid tiers.
- Build for individual voluntary adoption before enterprise aggregation.
- The format is earned by adoption, not declared by spec.
