# v2.71 — Pre-OSS review hardening: Design

Every item below was verified against current code during the review
(file:line cited in tasks.md).

## 1. Hook crash backstop (`cli_hooks.py`, collectors)

In `register()`, each hidden hook command becomes:

```python
def _safe_hook(fn): 
    try: return fn()
    except SystemExit: raise
    except BaseException: return 0   # a hook must never crash the host
```

Wrap every `raise typer.Exit(code=fn())` as
`raise typer.Exit(code=_run_hook(fn))`. Plus: payload numeric
extraction in `claude_code`/`gemini_cli` routed through a tolerant
`_coerce_int` (mirrors Cursor's existing `_optional_int`), and
`OSError` added to the `_read_state` catch in `claude_code`/`cursor`.

## 2. v2.38 escaping

`escape()` `remote` and `favorite_model` in `usage_pane.py`, `branch`
in `branch_modal._branch_label`. Extend `test_v238_review_hardening`
with a markup-bearing remote/branch through both widgets.

## 3. `tags` encoding

Serialize: `",".join(_encode_free_text(t) for t in tags)` (percent-
encoding has no comma, so the join delimiter is unambiguous). Parse:
split on `,`, `_decode_free_text` each element. Legacy `tags=a,b`
(no percent-encoding) decodes unchanged (`_decode_free_text` is a
no-op on bytes with no `%`). Round-trip + legacy test.

## 4. Milestone out of the append hot path

`append_session` drops the inline `parse_sessions` call. Milestone
easter-egg evaluation moves to an explicit `maybe_emit_milestones()`
called once by the stop-hook collectors (post-append) and skipped by
bulk importers. Behaviour preserved for the interactive path; bulk
import no longer O(n²).

## 5. SQLite concurrency

After `sqlite3.connect`: `PRAGMA busy_timeout=5000` and
`PRAGMA journal_mode=WAL`. WAL is durable across processes and the
file stays a rebuildable cache.

## 6. `--json` contract

A shared `_json_fail(msg)` in the report CLI emits `jsonio`
`{"error":…}` to stdout and exits 1; all human/diagnostic prints use
a module `err_console = Console(stderr=True)`. Every `--json` branch
routed through it.

## 7. `store.read_new_lines()`

`a ` (amendment) records are applied incrementally to the in-memory
session list (same `apply_amendment` the full parse uses) instead of
forcing `self.load()`. Full reload only on truncation/rotation.

## Lower-tier (mechanical, each cited in tasks.md)

`codex_app` 25MB cap + `islink` reject; `gemini_history` `islink`
reject + `find_session_file` `stat` `OSError` guard; `_do_install_
hook_claude` `_settings_unchanged` guard; `gemini_otel` max-attempts
on the recovery scan; `app.py` advisory excepts `self.log(...)`;
`ledger` accumulate Decimal; `db.last_sync()` tolerate unmigrated
schema; `pricing` `print`→Rich stderr; `pyproject` runtime upper
bounds; `project.md` test count.

## Tests

`tests/test_v271_review_hardening.py`: hook never raises on a
malformed payload (all 3 stop collectors); tag comma round-trip +
legacy; usage_pane/branch_modal markup escaped; bulk-append is not
O(n²) (no full re-parse per append — assert via call count/spy);
SQLite concurrent open does not raise; `--json` failure emits
`{"error":…}`+exit1; store applies `a ` without full reload;
codex/gemini_history reject symlink; install-claude no-op byte-stable.
Plus the v2.38 suite extension.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry. Feature-class changeset (cross-cutting hardening) — full spec.
