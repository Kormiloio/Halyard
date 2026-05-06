# Halyard

> *A halyard is the line that raises the sails. Pull on it, the sails go up. Pull on this one, your books go up.*

A plain-text, agent-native financial OS for freelancers. Your time, expenses, and invoices live as plain text on your laptop. An AI agent (Claude) reads and writes them on your behalf.

**Status:** pre-alpha. v0 in development. Watch the repo for the first release.

## The pitch

You run a freelance business. Your time tracking is in Notion or Toggl. Your invoices are in FreshBooks or QuickBooks. Your expenses are CSVs you've been meaning to deal with. Your data is locked in five different SaaS subscriptions, none of which talk to each other, all of which get more expensive every year.

Halyard is an alternative:

- **Local-first.** Everything lives in a folder on your computer. Git it, back it up, sync it however you want.
- **Plain text forever.** [hledger timeclock](https://hledger.org/timeclock.html) for time, [Beancount](https://beancount.github.io/) for ledgers, markdown for invoices. No proprietary formats. Compatible with the entire plaintext-accounting ecosystem on day one.
- **Agent-native.** "I worked 3 hours on ACME this morning" → entry written. "Draft an invoice for last month" → markdown + PDF generated. The agent edits the same files you can edit by hand.
- **Open source, MIT.** Yours forever.

## Quickstart

> Coming with v0.1.0. See [`openspec/changes/v0-time-and-invoice/`](./openspec/changes/v0-time-and-invoice/) for what's being built.

```bash
pipx install halyard
cd ~/businesses/my-freelance
halyard init
halyard
```

## How it's being built

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development. Every feature lives as a change folder under `openspec/changes/` with a proposal, specs, design, and tasks.

To see what's being built next, look at any folder under `openspec/changes/` that hasn't been moved to `openspec/changes/archive/`.

## Roadmap

- **v0** — time tracking + invoicing CLI + Claude REPL. *In progress.*
- **v1** — expense ingestion, local web UI at `localhost:7474`, plugin/skill system.
- **v2** — bank sync (Plaid), full bookkeeping automation, project profitability.
- **v3+** — tax forms, e-file. Distant future.

## Contributing

Too early. Star the repo and watch for v0.1.0.

## License

MIT.

---

A [Kormilo LLC](https://kormilo.io) project. *Kormilo* is Slavic for "rudder" — the helm of your business. Halyard is the first thing it builds.
