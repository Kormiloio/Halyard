# Data Model Spec

## Requirement: project layout

A Halyard project is a directory containing exactly these files at the root
after `halyard init`:

- `halyard.toml` — project config (business name, default currency,
  invoice counter, default invoice due-window in days)
- `clients.toml` — array of clients
- `projects.toml` — array of projects
- `time.timeclock` — append-only hledger timeclock file
- `invoices/` — directory of generated invoice `.md` and `.pdf` files
- `.gitignore` — excludes `*.pdf` if the user opts in, plus
  `.halyard-cache/` and `~/.halyard/`

## Requirement: halyard.toml schema

```toml
[business]
name = "M. Camaj Consulting"
currency = "USD"
default_due_days = 30

[invoicing]
counter = 0          # next invoice number suffix
prefix = "{year}-{month:02d}-{client_slug}"
```

## Requirement: clients.toml schema

```toml
[[client]]
slug = "acme"            # required, lowercase, [a-z0-9-]
name = "Acme Corp"       # required
hourly_rate = 150        # required, numeric
email = "ap@acme.com"    # optional
address = """            # optional, multi-line ok
123 Main St
Anytown, ST 12345
"""
```

## Requirement: projects.toml schema

```toml
[[project]]
slug = "auth-migration"   # required, scoped under client_slug
client_slug = "acme"      # required, must match a client
name = "Auth migration"   # required
hourly_rate = 175         # optional override; falls back to client rate
```

## Requirement: timeclock format

Time entries MUST conform to hledger timeclock format:

```
i YYYY-MM-DD HH:MM:SS <client-slug>:<project-slug>  optional comment
o YYYY-MM-DD HH:MM:SS
```

The file is parseable by `hledger` directly, with no Halyard-specific
extension. Compatibility with the broader plaintext-accounting ecosystem
is a hard requirement — users SHOULD be able to drop Fava or hledger-web
on top of `time.timeclock` and have it just work.

## Requirement: invoice format

Each invoice is a markdown file with YAML frontmatter:

```markdown
---
invoice_number: 2026-04-acme-001
client_slug: acme
issue_date: 2026-04-30
due_date: 2026-05-30
currency: USD
line_items:
  - description: Auth migration
    project_slug: auth-migration
    hours: 12.5
    rate: 175
    amount: 2187.50
total: 2187.50
---

# Invoice 2026-04-acme-001

(rendered body — generated from the template)
```

The body is rendered from `templates/invoice.md.j2` if present in the
project, otherwise from the built-in default template shipped with Halyard.

## Requirement: invoice number sequencing

Invoice numbers are sequential within a `(year, month, client)` tuple. The
counter in `halyard.toml` is global; the prefix template controls how that
counter renders into a final number.

### Scenario: first invoice of the month for a client

- WHEN the project has no prior invoice for ACME in 2026-04
- THEN the next invoice for ACME in that month is `2026-04-acme-001`

### Scenario: second invoice of the month for the same client

- WHEN the project already has `2026-04-acme-001`
- THEN the next is `2026-04-acme-002`

### Scenario: different clients, same month

- WHEN the project has `2026-04-acme-001` and the user invoices Globex
- THEN the next is `2026-04-globex-001`
