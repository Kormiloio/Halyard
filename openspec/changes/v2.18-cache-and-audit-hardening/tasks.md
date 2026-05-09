# Tasks

Implementation checklist for v2.18 — Cache and Audit Hardening.

## 1. Project registry

- [x] 1.1 Define `~/.halyard/projects` format (one absolute path per line).
- [x] 1.2 `halyard init` appends the new project to the registry.
- [x] 1.3 `halyard db sync` reads the registry first, then walks up from
  CWD as a fallback for any unregistered project.
- [x] 1.4 `halyard db sync --status` lists known project dirs.
- [x] 1.5 New `halyard projects list` and `halyard projects forget <path>`
  commands.

## 2. Schema migrations

- [x] 2.1 Add `_MIGRATIONS` list of `(from_version, sql)` tuples to db.py.
- [x] 2.2 `get_db` reads `PRAGMA user_version`, runs pending migrations.
- [x] 2.3 First migration: `v0 → v1` (no-op, establishes framework).
- [x] 2.4 Test: opening an old-version DB upgrades correctly.
- [x] 2.5 Test: opening a future-version DB raises a clear error.

## 3. Content-addressed session ID

- [x] 3.1 Replace `_session_id` to hash `(start, end, tool, model,
  input_tokens, output_tokens)`.
- [x] 3.2 Bump migration version: detect old hash format, prompt user to
  run `halyard db reset`. (Auto-reset is destructive enough to require
  consent.)
- [x] 3.3 Test: amending a session via `a` record does not create a
  duplicate cache row.

## 4. Invoice front-matter rates

- [x] 4.1 Update `invoice.md.j2` template to include `rates:` and
  `template_version: 2` in YAML front-matter.
- [x] 4.2 Update `_render_invoice` to populate front-matter rate data.
- [x] 4.3 Update `audit_invoices` to read front-matter first; fall back
  to regex with trust-label `inferred` for pre-v2.18 invoices.
- [x] 4.4 Test: v2.18 invoice audits against front-matter rates.
- [x] 4.5 Test: v2.15 (regex) invoice still audits with reduced trust.
- [x] 4.6 Test: custom template with `$` prefix audits correctly.

## 5. Test backfill — v2.12 service

- [x] 5.1 `tests/test_service.py`: install with mocked launchctl.
- [x] 5.2 Uninstall removes plist file and stops daemon.
- [x] 5.3 Status reports correct port from plist.
- [x] 5.4 Plist generation handles paths with special chars.

## 6. Test backfill — v2.12 dashboard POST

- [x] 6.1 `POST /api/start` with valid auth writes timeclock entry.
- [x] 6.2 `POST /api/stop` with valid auth invokes `stop_timer`
  (post-v2.17), runs backfill.
- [x] 6.3 Slug validation rejects `client/proj` (slash not allowed).

## 7. Test backfill — backfill_window

- [x] 7.1 Session straddles midnight: window includes both halves.
- [x] 7.2 Session start equals window end: not included.
- [x] 7.3 Multiple overlapping i/o pairs: backfill picks the most recent.
- [x] 7.4 Empty window: no error, returns 0.

## 8. Test backfill — audit git-history path

- [x] 8.1 Fixture: temp git repo with two commits to clients.toml that
  change a client's hourly rate.
- [x] 8.2 `rate_history_from_git` returns both rate changes with correct
  dates.
- [x] 8.3 Repo without clients.toml history: returns empty list.
- [x] 8.4 No `git` in PATH: returns empty list, no error.

## 9. Test backfill — hook auto-install

- [x] 9.1 Fixture: fake `$HOME` with no `~/.claude/settings.json`.
- [x] 9.2 `_auto_install_detected_hooks` writes the expected hook entries.
- [x] 9.3 Existing settings file is preserved (other entries untouched).
- [x] 9.4 Idempotent: running twice does not duplicate entries.

## 10. Documentation

- [x] 10.1 Document the project registry format in
  `openspec/project.md`.
- [x] 10.2 Document migration policy: every schema change ships a
  migration; `db reset` is the escape hatch.
- [x] 10.3 Update v2.14 spec to reference v2.18 amendments.
