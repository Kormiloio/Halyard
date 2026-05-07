# Design

## Architecture

The dashboard is a local web server embedded in the Halyard CLI. It reads
project files on demand and renders a local UI. The source of truth remains the
plain-text files.

Initial implementation should prefer a small Python-native stack over a
separate frontend build pipeline. The dashboard can evolve later, but the first
version should be easy to package with the CLI.

Recommended initial stack:

- server: FastAPI or Starlette;
- templates: Jinja2;
- styling: static CSS bundled with Halyard;
- updates: polling first, server-sent events later;
- bind address: `127.0.0.1` only by default.

If adding FastAPI is too heavy for v2, a Typer command backed by Python's
standard `http.server` plus Jinja templates is acceptable for the MVP.

## Command

```bash
halyard dashboard [--port 0] [--open] [--project <client/project>]
```

Behavior:

- `--port 0` picks an available port.
- The command prints the local URL.
- `--open` opens the URL in the platform browser.
- Without `--open`, no GUI app is launched.
- The server exits when the process exits.

## Views

### Glass Cockpit

The default route should be a modern operational overview. It should feel like
an instrument panel for AI work: dense, crisp, and live.

The cockpit shows:

- active timer and current project;
- capture health;
- today's human hours;
- today's AI sessions;
- token totals;
- direct and allocated cost;
- model/tool mix;
- latest session stream;
- warnings for missing, inferred, or unattributed data.

Visual direction:

- compact top-level metric tiles;
- one primary session stream;
- one project/cost table;
- small charts only when they improve scanning;
- semantic status colors;
- no marketing hero section;
- no decorative background effects;
- stable dimensions so live updates do not shift the layout.

### Today

Shows:

- active timer status;
- current project;
- human hours today;
- AI sessions today;
- input/output/cache token totals;
- direct API cost;
- allocated plan cost;
- latest captured session.

### Projects

Shows one row per project:

- client/project;
- human hours for selected period;
- AI sessions;
- AI cost;
- top tool;
- top model;
- unattributed/inferred warnings;
- invoice evidence readiness.

### Sessions

Shows parsed `ai-sessions.log` records with filters:

- date range;
- project;
- tool;
- model;
- source;
- attribution state.

### Costs

Shows:

- API costs from captured records;
- credit costs when configured;
- seat allocations from `ai-plans.toml`;
- costs that cannot be calculated yet;
- trust labels: captured, calculated, allocated, inferred, missing.

### Health

Shows:

- project discovery state;
- required files present;
- `ai-sessions.log` writable;
- Claude Code hook installed locally or globally;
- active timer state file status;
- latest collector write timestamp;
- pricing table snapshot/version;
- unattributed session count.

## Data access

The dashboard must reuse the same parsers and report services as the CLI. If
the CLI does not yet have report service boundaries, this change should extract
them before adding dashboard-only logic.

The dashboard may read:

- project files under the Halyard project root;
- selected state files under `~/.halyard/`;
- `.claude/settings.json` only for hook health checks.

The dashboard must not read arbitrary user files.

## Writes

MVP is read-only. Later write flows, such as confirming inferred attribution,
must use the same approval model as the CLI and show the exact file diff before
writing.

## Security

- Bind to `127.0.0.1` by default.
- Do not expose on the LAN unless the user explicitly asks for it.
- Do not include secrets, API keys, prompts, transcripts, or code contents.
- Do not add telemetry.
- Add a random local session token if write actions are introduced later.

## Packaging

Static assets and templates should ship inside the Python package. The
dashboard should not require Node, npm, or a frontend build step for the MVP.
