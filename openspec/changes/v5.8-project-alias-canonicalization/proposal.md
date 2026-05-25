# v5.8 — Project alias canonicalization (read-time)

## Why

One logical project accumulates several slug forms in the append-only log as the
attribution chain evolves: e.g. `git/Halyard` (unmapped git remote, "git-auto"
rung), `kormilo/halyard` (older auto form), and `kormilo:halyard` (the canonical
`client:project` slug). Every surface — dashboard cost donut, top-projects,
Moat evidence, `report`, invoices, MCP — then splits one project's cost three
ways. v5.7 added a display-only `_norm_project` stopgap in the dashboard with a
hard-coded alias; this replaces it with a real, single canonicalization point.

The merge cannot be inferred safely: `kormilo/halyard` ↔ `kormilo:halyard` is a
separator drift, but `git/Halyard` ↔ `kormilo:halyard` is a human fact (the
remote *is* that project) only the owner knows. So canonicalization is driven by
a **user-defined alias map**, not a heuristic.

## What changes

1. **`~/.halyard/project-aliases.toml`** — a dedicated, user-editable
   `[aliases]` table mapping a source slug → canonical slug. Separate from
   `repos.toml` (which is remote→slug *derivation*; this is post-attribution
   *canonicalization*, and a shared file would be clobbered by `register_repo`).
2. **`attribution.canonical_project()`** + `load_project_aliases()` /
   `set_project_alias()`.
3. **Applied once at the `parse_sessions` read boundary** (after amendment
   folding), so every surface sees the canonical slug. **The log is never
   rewritten** — read-time reinterpretation only (append-only / trust
   principles, like the v2.53/v2.54 read guards). Writes (collectors) keep
   emitting whatever slug attribution derives.
4. **`halyard alias-project <source> <canonical>` / `--list`** CLI to manage the
   map (diff-free config write, mirroring `link-repo`).
5. **Remove the v5.7 `_norm_project` dashboard stopgap** — the Overview charts
   now receive already-canonical slugs from `parse_sessions`.

## Impact

- Affected: `src/halyard/attribution.py` (alias map + canonical_project),
  `src/halyard/ai_log.py` (apply at parse boundary, local import to avoid the
  attribution→ai_log cycle), `src/halyard/dashboard.py` (drop `_norm_project`),
  a CLI module (`alias-project`), `tests/`.
- **Billable note:** this re-groups historical cost by canonical slug
  everywhere, including invoices/report. That is the intent and is owner-driven
  (the map is explicit, never heuristic). The raw log is unchanged and remains
  the auditable source of truth.
- Out of scope: auto-normalizing separators for `git/` auto-slugs (the `git/`
  prefix deliberately signals "unmapped"; auto-merging it would be guessing).
