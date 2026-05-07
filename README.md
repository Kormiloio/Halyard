# Halyard

> *A halyard is the line that raises the sails. Pull on it, the sails go up. Pull on this one, your AI work comes into focus.*

**AI work intelligence infrastructure.** Time, tokens, models, and cost — captured where the work happens, owned by you, readable by anyone.

**Status:** pre-alpha. v0 in development. Watch the repo for the first release.

---

## The problem

You're doing AI-assisted work. So is your team. So is every engineering department at every company that's serious about staying competitive.

Nobody knows what it's actually costing. Nobody can measure whether it's working. Time tracking tools don't know about tokens. Finance dashboards don't know which model you used. Productivity tools don't capture the mix of human judgment and AI execution that makes modern work happen.

The instruments don't exist yet. Halyard builds them.

---

## Two audiences, one platform

**For the individual developer or freelancer:**
Your time, your AI spend, and your invoices live as plain text on your laptop. An AI agent (Claude) reads and writes them on your behalf. Git it, back it up, sync it however you want. No SaaS subscription required. No proprietary format. Compatible with the entire plaintext-accounting ecosystem.

**For engineering teams and enterprises:**
A unified view of AI work across your organization — spend by team, by project, by model, over time. Cost attribution. Productivity trends. Compliance audit trails. The data your CTO needs to answer "what are we getting for our AI investment?"

The solo developer experience is the entry point. The enterprise layer is optional, additive, and built on the same open data format.

---

## How it works

Halyard has two layers:

**Collection** — Lightweight agents that run where AI work happens. Claude Code hooks, API proxies, SDK wrappers. Every AI session is captured: time, tokens, model, cost, project. Written to a plain-text log you own. Open format, open source.

**Intelligence** — Analytics built on that log. Local CLI reports for solo users. Team dashboards and cost allocation for organizations. The same data, different lenses.

**Glass Cockpit** — A local dashboard for watching capture happen. Run `halyard dashboard` inside a Halyard project to see the active timer, recent AI sessions, token totals, cost, attribution, model mix, and collector health from the same plain-text files.

---

## Quickstart

> Coming with v0.1.0. See [`openspec/changes/v0-time-and-invoice/`](./openspec/changes/v0-time-and-invoice/) for what's being built.

```bash
pipx install halyard
cd ~/businesses/my-freelance
halyard init
halyard start acme/auth-migration
# ... do AI-assisted work ...
halyard stop
cat time.timeclock   # plain text, hledger-compatible
halyard dashboard    # local Glass Cockpit for AI work capture
halyard sample-session  # seed demo AI usage if hooks are not firing yet
```

---

## How it's being built

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development. Every feature lives as a change folder under `openspec/changes/` with a proposal, specs, design, and tasks.

- [`v0-time-and-invoice`](./openspec/changes/v0-time-and-invoice/) — time tracking + invoicing CLI. *In progress.*
- [`v1-ai-intelligence`](./openspec/changes/v1-ai-intelligence/) — AI usage event schema + Claude Code collector + local analytics. *Proposed.*
- [`v3-org-admin-dashboard`](./openspec/changes/v3-org-admin-dashboard/) — team, manager, CIO, governance, and finance rollups. *Proposed.*

---

## Roadmap

- **v0** — time tracking + invoicing CLI + Claude REPL. *In progress.*
- **v1** — AI usage event schema, Claude Code collector, API proxy collector, local `halyard report`.
- **v2** — team sync, web dashboard, cost allocation by project/model/person.
- **v3** — org admin dashboard: manager/CIO rollups, governance, finance exports, SSO.
- **v4+** — productivity measurement, ROI reporting, outcome-based billing support.

---

## Non-negotiables

These hold at every tier:

- **Local-first.** The core product runs offline. Cloud is optional and additive.
- **Plain text forever.** Your data is yours, in formats that outlast any startup.
- **Files are the source of truth.** No hidden state, no proprietary database.
- **No silent writes.** Every AI-proposed change is shown to you before it's written.
- **MIT licensed.** Permissively. Forever.

---

## Contributing

Too early. Star the repo and watch for v0.1.0.

## License

MIT.

---

A [Kormilo LLC](https://kormilo.io) project.
