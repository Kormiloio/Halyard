# v2.71 — Pre-OSS review hardening

## Why

A full multi-pass code review (collectors/hooks, core data model, TUI/
dashboard, DB/CLI/cross-cutting) ahead of the OSS release surfaced a
set of verified defects. None are architectural — the design held up
well — but several violate stated invariants and must not ship.

## What changes

**Ship-blockers (invariant violations):**

1. **Hook crash backstop.** Hidden hook entry points
   (`cc-hook`/`gc-hook`/…) only have `DbError` caught in `main()`; any
   other exception (e.g. `int()` on a malformed payload) crashes the
   host tool. Add a catch-all at every hook entry point (log + exit 0)
   and route payload numeric coercion through a tolerant helper.
2. **v2.38 markup-injection regressions.** `usage_pane` (remote,
   favorite_model) and `branch_modal` (branch) render untrusted
   external strings unescaped — the exact class the v2.38 suite
   exists to prevent, in widgets it never covered. Escape + extend
   the test.
3. **`tags` round-trip corruption.** Tags are joined/split on `,`
   while `_safe_field` does not neutralize commas. Use the existing
   `_encode_free_text`/`_decode_free_text` per element; keep reading
   legacy comma form.

**High-value:**

4. `append_session` full-re-parses the log on every append for
   milestone easter eggs → O(n²) on bulk import. Lift milestone
   evaluation out of the per-append hot path.
5. SQLite opened with no `busy_timeout`/WAL → uncaught
   `OperationalError` under concurrent dashboard/service/CLI access.
6. `--json` error contract: every `--json` failure emits
   `{"error":…}` and diagnostics go to stderr, not stdout.
7. `store.read_new_lines()` full-reloads on every `a ` record
   (written routinely by `outcome sync`), defeating the tail.

**Lower:** consistent bounded-read hardening across collectors
(`codex_app` size cap + symlink reject, `gemini_history` symlink
reject + stat guard, `_read_state` `OSError`), `_do_install_hook_
claude` byte-stable no-op, `gemini_otel` recovery-scan cap, `app.py`
broad-except logging, `ledger` Decimal accumulation, `last_sync()`
read-only, pricing `print`→Rich, dependency upper bounds, and the
stale test-count in `project.md`.

## Constraints honored

- **Backward compatible.** Legacy `tags=a,b` still parses; old logs
  unaffected. No schema break.
- **No new invariants, only enforcement of existing ones.**
- **Hooks never crash the host** is strengthened, not relaxed.

## Non-goals

- Signed/authenticated amendment records (noted as a known
  trust-model gap; same posture as the v2.53 synthetic guard, not
  expanded here).
- Preserving unknown future kv tokens through a rewrite path (no
  rewrite path exists; documented, not built).
