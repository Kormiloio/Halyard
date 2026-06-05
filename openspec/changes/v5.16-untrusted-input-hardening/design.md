# v5.16 — Design

## Principle: validate at the boundary, once

Each untrusted value is sanitized/validated at the single point it enters
Halyard's trusted core — the parse choke point, the path-join, the
subprocess arg list — not defensively at every downstream consumer. Where a
crash is machine-wide (B1), we add one defensive backstop at the aggregation
choke point as well, but the boundary fix is primary.

## B1 — non-finite floats

`float("inf")`, `float("1e400")`, and `float("nan")` all parse without error
and all satisfy `x < 0 == False`, so the existing non-negativity guards admit
them. Two parse sites in `ai_log.py`:

- Positional `cost_usd` (~992): a non-finite value should **reject the whole
  line** (return `None`), exactly as a negative cost already does — a line
  this malformed is not a trustworthy session.
- `FLOAT_4` `credits` handler (~1016): a non-finite value should **skip the
  field** (leave it `None`), matching the handler's existing
  skip-on-`ValueError` behavior for a single bad field.

Backstop: `usage.sum_spend` (~46) skips `not math.isfinite(s.cost_usd)` so a
non-finite arriving via the SQLite cache (`db.py`) or direct `AiSession(...)`
construction degrades to a dropped value instead of `InvalidOperation`/`NaN`.
This is secondary; per the audit, the parse-side rejection is the real fix.

The serialization path (`to_log_line`, ~600 `f"{val:.4f}"`) needs no change:
once parse and construction reject non-finite, no non-finite value can reach
it.

Python 3.11+'s `int()` 4300-digit string limit already rejects pathological
integer token strings (`int("9"*5000)` raises `ValueError`, caught at ~977),
so the token-count DoS needs no code change.

## B7 — windsurf path traversal

Sanitize `trajectory_id` to `^[A-Za-z0-9._-]+$` (reject empty, `/`, `..`,
absolute). After building the state path, `Path.resolve()` and assert it is
relative to the resolved `ws-sessions/` root before any `mkdir`/`write`. Two
layers because slug-sanitization alone can miss edge cases; the resolved-root
assertion is the authoritative containment check.

## B8 — collector parse robustness

The parsers document "return None on any error" but only catch `OSError`.
Broaden the per-file guard to `(OSError, ValueError, TypeError,
OverflowError)` and add a safe-int helper for token coercions. Independently,
guard the importer loops (`run_gemini_import`, `import_codex_sessions`, etc.)
so a `None`/raise from one file logs-and-skips rather than aborting the batch
— defense in depth, since a future parser bug shouldn't nuke a whole import.

## B9 — git ref injection

Every call site that interpolates a session-derived git ref into a `git`
argv must (1) place a literal `"--"` before the ref so git cannot parse it as
an option, and (2) validate the ref against `^[0-9a-fA-F]{4,40}$` and skip the
diff if it fails. Both, not either: `--` stops option injection, the regex
stops a malformed ref reaching git at all. Call sites: `git_context.py:150`,
`cursor.py:121`, `claude_code.py:233` (grep for the pattern to catch any
others).

## B10 — gh endpoint + log injection

Add `_valid_repo(repo) -> bool` (`^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$`, and
reject any component equal to `.`/`..`) and call it before every `gh api
repos/{repo}/...`. Route `_write_amendment` field values through the same
`_safe_field` / SAFE_FIELD encoding `to_log_line` uses, so spaces, `=`, and
newlines cannot forge fields or inject a second record.

## B19 — Rich markup injection

`rich.markup.escape(...)` the MCP phrase in `render_mcp_phrase`
(`leverage.py:172`), matching the escaping discipline already used in
`session_feed`/`project_pane`/`moat_pane`/`usage_pane`. Additionally
re-apply `MCP_SERVER_ALLOWLIST` in `summarize_mcp` so non-allowlisted strings
never reach the renderer at all (the allowlist is currently applied only at
write time, which a hand-edited log bypasses).

## Testing

Each blocker gets a focused regression test asserting the malicious input is
neutralized AND a benign input still works (no over-restriction). Tests use
the existing `tmp_path` + `append_session`/raw-write fixtures.
