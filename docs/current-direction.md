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

## Outcome-Aware Metadata Gap

As of May 2026, the session model scores 2/10 on outcome awareness. The
current state:

| Signal | Status |
|---|---|
| Branch name | Captured — but stored as a tag string, not a first-class field |
| `code_added` / `code_removed` | First-class fields — Gemini only |
| `tool_calls` / `wall_seconds` | First-class fields — Gemini only |
| Commit count in session window | Not captured |
| PR linkage / PR outcome | Not captured |
| Repeated attempts on same ticket | Not captured |

Moving from 2/10 to 6/10 is the named initiative in v2.24. It requires:

1. **Branch as a first-class field** — the data is already captured by all
   collectors, but stored as a tag. Promote to `branch: str | None` on the
   `AiSession` dataclass.
2. **Commit count at session close** — run `git log --since --until` at stop
   time in all collectors. One new function in `git_context.py`.
3. **Code delta for Claude/Cursor/Codex** — approximate via
   `git diff --numstat` over commits in the session window. Trust label:
   `calculated`.
4. **PR linkage** — `halyard outcome sync` command queries `gh pr list`,
   appends `a <hash> pr_ref=... pr_state=...` amendment records. New
   `outcomes` and `pr_cache` SQLite tables (requires v2.18 migration
   framework first).

Spec: `openspec/changes/v2.24-outcome-metadata/`.

---

## Current Build Sequence

1. **v2.18** — Cache and audit hardening: project registry, schema migrations,
   content-addressed session IDs, invoice front-matter rate fields, test
   backfill for v2.11–v2.15.
2. **OSS launch** — HN / Reddit / Lobsters. Gate: `pipx install halyard &&
   halyard init` works end-to-end in a clean venv. Goal: real users, not
   stars.
3. **v2.24** — Outcome metadata uplift: branch field, commit count, code
   delta for all collectors, PR linkage via `halyard outcome sync`.
4. **v2.19** — Attestable AI work appendix. Gated on v2.24 so the appendix
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
