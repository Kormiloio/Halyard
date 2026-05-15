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
14. **v2.19** — Attestable AI work appendix. Gated on v2.24 so the appendix
   can include commit and PR evidence.
5. **v3.0** — Outcome graph (connect sessions to commits, PRs, tests) only
   if design partners ask for it.
6. **v3+ org and enterprise** — After the local proof artifact is in the
   field and the security posture is credible.

---

## What Is Deferred

These ideas are important, but not the current wedge:

- hosted dashboards;
- SSO / RBAC;
- org admin dashboards;
- full outcome graph analytics (v3.0);
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
