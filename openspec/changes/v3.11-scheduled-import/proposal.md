# Proposal: v3.11 — `import-all` + scheduled importer

## Why this exists

Codex, Copilot, and Gemini are **import-based** collectors: their sessions
only reach the ledger when an importer runs. Without a schedule they silently
lag between manual `import-*` invocations — a freshness gap adjacent to the
Gemini outage (a tool can look "captured" while its newest work sits
un-imported on disk). A capture-audit of all tools (the parent investigation)
recommended wiring the importers into a recurring run.

## What changes

- **`halyard import-all`** — runs the Codex, Copilot, and Gemini importers in
  one idempotent pass (`all_projects=True`); already-imported sessions are
  skipped via their `job_id`/import-state. The Gemini importer body is
  extracted to a reusable `cli_importers.run_gemini_import(...)` shared by
  `import-gemini` and `import-all` (no behaviour change to `import-gemini`).
- **`halyard install-import-timer` / `uninstall-import-timer`** — a macOS
  LaunchAgent (`import_timer.py`, modeled on `service.py`) that runs
  `import-all` on a `StartInterval` (default 30 min) so importer tools stay
  current with no manual step. XML-escaped plist, absolute `_halyard_exe()`
  path, idempotent load.

## Scope / care

- **Not auto-activated.** Installing the timer creates an autonomous background
  *writer* of user data, so it is opt-in via the explicit command — never
  installed implicitly. macOS-only for now (launchd); the command exits with a
  clear message elsewhere.
- **First run bulk-imports existing on-disk history.** This is correct for
  never-captured sessions, but a handful of 2026-05-07 Gemini sessions were
  already recorded by the old hook (no `job_id`, so the importer can't dedup
  them) and would double-count. The parent investigation backfilled only the
  one target session deliberately for this reason; a clean historical
  reconcile (or accepting the small overlap) should precede enabling the timer.
- The v3.10 coverage canary independently flags any importer/collector that
  falls behind, so a missed schedule is still visible.

## Also fixed: cwd-dependent importer dedup (found while enabling the timer)

Enabling the timer surfaced a real dedup bug. `run_gemini_import` built its
"already imported" set only from the **current** project (`find_project_dir()`)
+ hub, but routes each session to its **per-slug** target project. A run from a
different working directory — exactly what a launchd job is — therefore didn't
see the per-slug logs and **re-imported every session on every run**, creating
duplicates (observed: each scheduled run re-added 7 Gemini rows). Fix: dedup
against the dir each session actually routes to (`_existing_gemini_ids`, cached
per dir), so dedup is cwd-independent. Regression test asserts a session
already in its target log is skipped even when the importer runs from an
unrelated cwd. Operational: the duplicates created while diagnosing this were
cleaned by a job_id-dedup pass over all project + hub logs (backups kept).

## Deployment note

`uv tool install --force .` reused a **cached wheel** (same 0.2.1 version), so
the first reinstall shipped stale code; `--reinstall --no-cache` is required to
rebuild from working-tree source. Verified the installed binary the LaunchAgent
runs contains the dedup fix and that its RunAtLoad first run is a clean no-op
(no duplicates).

## Success criteria

- `halyard import-all` runs all three importers and reports per-tool counts;
  re-runs skip already-imported sessions.
- The LaunchAgent plist is valid, runs `import-all` on the interval, and is
  XML-injection-safe. ruff/mypy clean; suite green.
