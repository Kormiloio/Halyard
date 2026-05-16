# v2.52 — Unwired-Tool Detection Nudge: Design

## Where the code goes

`src/halyard/doctor.py` only. Add one new check group,
`_unwired_tool_checks()`, appended in `build_doctor_report()` right
after `_hook_checks(...)` (doctor.py:54). Output is ordinary
`DoctorCheck` objects, so `render_text`, `render_json`, `has_errors`,
and every surface that consumes `DoctorReport` (dashboard/TUI health)
pick it up for free.

## Detection logic

For each live-hook tool `t` in `("claude", "cursor", "gemini")`:

```
on_path   = shutil.which(<binary for t>) is not None
has_hook  = existing _<t>_hook_check(...) status == "ok"
has_mcp   = _mcp_registered(t)        # new tiny helper
if on_path and not has_hook and not has_mcp:
    -> DoctorCheck(id=f"unwired.{t}", status="warning",
                    label=<Label> + " (installed, not wired)",
                    detail="detected on PATH but no Halyard hooks or MCP server",
                    fix=f"halyard setup  (or halyard install-hook-{t})")
```

`_mcp_registered(t)` reads the v2.51 `_MCP_CLIENTS[t]` config file and
checks for an `mcpServers.halyard` whose command basename is
`halyard` — mirrors the existing `_is_halyard_hook_cmd` basename
matching so a moved venv still counts as wired.

Codex (import model — no hook, no MCP). As-built: two read-only
helpers were added to `codex_app` (recomputing paths from
`Path.home()` so tests with a relocated home work):

- `codex_history_present()` — `~/.codex/sessions` exists AND contains
  at least one `rollout-*.jsonl`.
- `codex_imported_any()` — the dedup state file
  `~/.halyard/codex-imported` exists and has ≥1 non-empty line. (This
  is cheaper and more robust than scanning the ledger for
  `tool == "codex"` sessions, and is the importer's own source of
  truth for what has been imported.)

```
if codex_history_present() and not codex_imported_any():
    -> DoctorCheck(id="unwired.codex", status="warning",
                    label="Codex (unwired)",
                    detail="Codex Desktop history on disk but none imported",
                    fix="halyard import-codex")
```

Only evaluated when `tool == "all"` (Codex has no `ToolScope`).

## Status semantics

- `warn`, never `error`: an unwired tool is not a broken Halyard
  install, just an incomplete one. `has_errors()` stays false so
  `halyard doctor` exit code is unaffected (scripts/CI don't break).
- A tool wired by hooks **or** MCP for its scope produces no check
  (silent = fine). The nudge is strictly "installed AND zero
  integration".

## Rendering

`render_text` already groups checks; the new ones slot in with the
standard `warn` glyph and the `fix:` line. No template changes. JSON
output gains the `unwired.*` ids automatically via `to_jsonable()`.

## Tests (`tests/test_v252_tool_detection.py`)

`monkeypatch.setattr(Path, "home", tmp)` + monkeypatch `shutil.which`:

1. Binary on PATH, no hooks, no MCP → exactly one `unwired.<t>` warn
   with the documented `fix`.
2. Binary on PATH **with** hooks → no `unwired` check (hook satisfies).
3. Binary on PATH **with** MCP only (no hook) → no `unwired` check
   (MCP satisfies).
4. Binary absent → no `unwired` check.
5. Codex history dir present + zero codex sessions in ledger →
   `unwired.codex` warn, fix `halyard import-codex`.
6. Codex history present + a codex session already in ledger → no
   check.
7. `has_errors(report)` stays False with only `unwired.*` warns
   (exit-code contract preserved).
8. `render_json` includes the `unwired.*` ids.

## Gate

Full `pytest` + `ruff check` + `ruff format --check` + `mypy src/`.
Roadmap entry status flips to complete only when built. README
`doctor` mention (if any) updated to note the unwired-tool nudge.
