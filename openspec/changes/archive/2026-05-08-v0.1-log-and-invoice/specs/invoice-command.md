# Spec: `halyard invoice` — Invoice Generator

## Overview

`halyard invoice <client> [--project <slug>] [--period <YYYY-MM>]` reads the
project's `time.timeclock`, `clients.toml`, `projects.toml`, and `halyard.toml`
and renders a Jinja2 invoice markdown file.

---

## Scenarios

### WHEN the user runs `halyard invoice acme`
THEN the command reads all closed time entries for projects linked to client
`acme`, in the current billing period (current calendar month by default),
renders the invoice using the bundled template, increments `invoice_counter` in
`halyard.toml`, and writes the file to `invoices/YYYY-MM-{counter:03d}-acme.md`.
A confirmation line is printed: `Invoice written: invoices/2026-05-001-acme.md`

### WHEN the user passes `--project auth-migration`
THEN only time entries tagged to `acme:auth-migration` are included.

### WHEN the user passes `--period 2026-04`
THEN only time entries with clock-out dates in April 2026 are included.

### WHEN the user passes `--dry-run`
THEN the rendered invoice is printed to stdout and nothing is written to disk.
The `invoice_counter` is NOT incremented. The output is identical to what would
be written.

### WHEN the user passes `--pdf`
THEN after writing the markdown file, the command runs `typst compile
<markdown-path>` as a subprocess to produce a PDF alongside the markdown.
If typst is not installed (command not found), the command prints:
`typst not found — PDF skipped. Install typst to enable PDF output.`
and exits 0 (the markdown file was still written successfully).

### WHEN `clients.toml` has no entry for the specified client slug
THEN the command prints: `Client 'acme' not found in clients.toml.` and exits
with code 1. No file is written.

### WHEN there are no closed time entries for the client/period
THEN the command prints: `No closed time entries found for acme in 2026-05.`
and exits with code 1. No file is written.

### WHEN there are open (not clocked out) time entries for the client in the period
THEN the command prints a warning: `Warning: N open time entries found for
acme — clock out before invoicing.` The invoice is still generated from the
closed entries. The open entries are listed by start time.

### WHEN `include_ai_cost_in_invoice = true` is set in `halyard.toml`
THEN the invoice includes an AI usage line item: the total AI session cost
(from `ai-sessions.log`, filtered to the same client/project/period) as a
separate line below the time entries with label "AI usage cost".

### WHEN an invoice file for the same period and client already exists
THEN the command prints: `Invoice already exists: invoices/2026-05-001-acme.md.
Use --force to overwrite.` and exits with code 1.

### WHEN the user passes `--force` alongside an existing invoice path
THEN the existing file is overwritten. The counter is NOT incremented again.

---

## Invoice template

The bundled template produces:

```markdown
---
invoice_number: "2026-05-001"
client: Acme Corp
date: 2026-05-31
period: May 2026
currency: USD
---

# Invoice #2026-05-001

**Acme Corp**
Billing period: May 2026

| Description | Hours | Rate | Amount |
|-------------|-------|------|--------|
| auth-migration | 12.5 | $150 | $1,875.00 |

**Total: $1,875.00**
```

Users can override the template by placing a file at `templates/invoice.md.j2`
in the project directory. The bundled template is used if no override exists.

---

## CLI flags

| Flag | Description |
|------|-------------|
| `--project <slug>` | Filter to a specific project under the client |
| `--period <YYYY-MM>` | Billing period (default: current month) |
| `--dry-run` | Preview invoice without writing or incrementing counter |
| `--pdf` | Generate PDF via typst after writing markdown |
| `--force` | Overwrite an existing invoice file for the same period |
| `--rate <amount>` | Override the hourly rate from `projects.toml` |
