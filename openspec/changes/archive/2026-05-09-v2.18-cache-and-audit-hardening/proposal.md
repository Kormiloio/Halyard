# Proposal: v2.18 — Cache and Audit Hardening

## Why

The v2.15 deep code review found four issues in the v2.14 SQLite cache
and the v2.15 invoice audit that produce silent wrong answers, not loud
failures. They must be fixed before either feature is recommended to
external users.

- **H4 — Cache discovery is CWD-only and lacks migrations.** `sync_all`
  walks up from CWD plus the hub, missing projects elsewhere on the
  filesystem. Schema additions in future versions will fail at read time
  with no migration path.
- **H5 — Cache deduplication breaks under attribution rewrites.** The
  session ID is `sha256(raw_line)`, which changes every time the line is
  amended (pre-v2.17) or via the new `a` records (post-v2.17). Next sync
  inserts a duplicate row, double-counting attributed sessions until
  `db reset`.
- **H6 — Invoice audit regex is fragile.** `_parse_invoice_rates` uses
  regex over rendered markdown rate columns. Currency prefixes (`$`,
  `€`), thousands separators, custom templates, and column reorderings
  all break it silently — audit reports clean when it shouldn't.
- **M2 — Test gaps for v2.11–v2.15.** No coverage for: dashboard `do_POST`
  endpoints, LaunchAgent install round-trip, `backfill_window` overlap
  cases, `audit_invoices` git-history path, hook auto-install integration.

## What changes

1. **Project registry.** New file `~/.halyard/projects` lists every
   project Halyard knows about. `halyard init` registers; `halyard db
   sync` reads the registry plus the hub. CWD walk-up is the fallback,
   not the primary source.

2. **Schema migrations.** Use `PRAGMA user_version` to track schema
   version. Migrations live in `db.py` as a list of `(from_version,
   migration_sql)` tuples. `get_db` runs pending migrations on open.
   First migration is a no-op (`v0 → v1`) to establish the framework.

3. **Content-addressed session ID.** Replace `sha256(raw_line)` with
   `sha256(start|end|tool|model|input_tok|output_tok)`. The ID is now
   stable across attribution amendments. `halyard db reset` is required
   for upgrade, with a clear migration message.

4. **Invoice rate fields in front-matter.** Generated invoices include
   explicit rate data in their YAML front-matter:

   ```yaml
   rates:
     - description: Engineering
       hours: 10
       rate: 150.00
       currency: USD
       amount: 1500.00
   template_version: 2
   ```

   `audit_invoices` reads from front-matter, not regex over the rendered
   table. Pre-v2.18 invoices fall back to the legacy regex path with a
   trust label of `inferred`.

5. **Test backfill for v2.11–v2.15.** New test files cover:
   - LaunchAgent install/uninstall/status round-trip (mocked launchctl).
   - Dashboard POST `/api/start` and `/api/stop` with auth.
   - `backfill_window` overlap, multi-day, midnight-straddling sessions.
   - `audit_invoices` git-history path with a fixture git repo.
   - Hook auto-install integration: writes the expected files in a
     fake `$HOME`.

## What stays the same

- The SQLite cache remains a derived read model. Plain-text files are
  still the source of truth.
- `halyard db sync` is still user-triggered; no background sync.
- The invoice template format is forward-extended (front-matter keys
  added) but not breaking-changed; existing parsers still work.
- The audit CLI surface (`halyard config audit`) is unchanged.

## Out of scope

- Real-time / continuous cache sync. Still on-demand.
- Multi-user / networked SQLite. Still single-user, single-machine.
- Multi-currency invoice support beyond the new `currency` field. Logic
  unchanged from v2.15.
- v2.11/v2.12/v2.13/v2.14/v2.15 feature changes — only test coverage.

## Success criteria

- A user with three projects in three different filesystem locations
  runs `halyard db sync` from anywhere and gets all three synced.
- Adding a new column to `sessions` ships with a migration; existing
  caches upgrade transparently.
- After v2.17 + v2.18: amending a session 5 times produces exactly 1 row
  in `sessions`, with the latest attribution.
- A custom invoice template with `$` prefixes and thousands separators
  audits correctly against `[[client.rate_history]]`.
- Test count climbs by at least 30 across the listed gaps.
