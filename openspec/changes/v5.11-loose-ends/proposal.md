# v5.11 — Loose ends (alias map, log hygiene, test isolation, Windows CI)

## Why

Four small, unrelated loose ends carried over from the v5.3–v5.10 arc. None is
big enough for its own changeset; batching them keeps the history honest.

## What changes

1. **Committable, in-repo project alias map.** The read-time alias map
   (`canonical_project`, v5.8) lives only at `~/.halyard/project-aliases.toml`
   — per-machine, never shared. A user on a second machine (or a teammate) loses
   the slug merges. `load_project_aliases` now also reads a committed
   `<project_dir>/project-aliases.toml` and merges it with the home file
   (committed = shared baseline, home = local override). `set_project_alias`
   writes to the committed project file when a project dir is known, so new
   aliases land in version control. Real user projects commit it (the `init`
   .gitignore template never ignored the ledger data). **This product repo is
   also the dev's data dir**, so `project-aliases.toml` is added to the *repo's*
   `.gitignore` (alongside `time.timeclock` etc.) to keep the dev's personal
   aliases out of the OSS release — no migration here.

2. **`log_diagnostic` newline hygiene.** A diagnostic message containing a
   newline broke the one-entry-per-line contract (a multi-line `msg` wrote
   several lines, corrupting downstream line parsing). `msg`/`tool`/`project`
   are now flattened to a single line before write.

3. **Tests stop writing the real `~/.halyard` logs.** Many tests call code paths
   that hit `log_diagnostic` / the audit log, which resolve to the *real*
   `~/.halyard/diagnostic.log` and `halyard.log` (module-level `Path.home()`
   constants). A conftest autouse fixture (mirroring v5.10's
   `_isolate_auto_timer`) redirects both to throwaway paths for every test.

4. **Real Windows CI.** The v5.9 Windows read-lock crash fix was only verified
   platform-agnostically; CI runs ubuntu-only. A non-blocking `test-windows`
   job runs the suite on `windows-latest` so the read-lock path is exercised on
   real Windows every push/PR. Non-blocking until proven green (we have no
   Windows machine to pre-verify on).

## Impact

- Affected: `attribution.py` (alias load/write + cache), `ai_log.py`
  (`log_diagnostic`; pass `project_dir` to `load_project_aliases`), `budget.py`,
  `invoicing.py`, `hub_server.py`, `cli_projects.py` (alias command), new
  `<project>/project-aliases.toml`, `tests/conftest.py`, `.github/workflows/ci.yml`.
- No log/format contract change; the append-only log is untouched. Alias
  resolution stays read-time only.
