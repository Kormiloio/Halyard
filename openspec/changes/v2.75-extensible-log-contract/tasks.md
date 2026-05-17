# v2.75 — Extensible log contract: Tasks

Status: **COMPLETE 2026-05-17 (1275 tests passing).** Closes the
v2.71 silent-drop gap; the line format is now extensible — consumers
(incl. Halyard-Enterprise) add tokens without forking the parser.

## Build
- [x] `AiSession.extra: dict[str,str]` (default_factory, `compare=False`
  — equality / `_session_id` / `session_hash`-of-empty-line unaffected)
- [x] Parser `case _:` preserves unknown `key=value` (percent →
  `_decode_free_text`, else raw); `_EXTRA_KEY_RE` rejects malformed
  keys; known cases matched first ⇒ no shadowing
- [x] `to_log_line` re-emits `extra` sorted-by-key, after known
  fields, via `_encode_free_text` (injection-safe, byte-stable empty)

## Hard invariants (tests, `tests/test_v275_extensible_log.py`, 8 cases)
- [x] round-trip lossless incl. space/`=`/`%`/unicode/comma values
- [x] `extra=={}` ⇒ byte-stable: re-serialize identical, session_hash
  of the empty-extra line unchanged ⇒ existing on-disk amendments
  still join
- [x] no shadowing: a known-field key never lands in `extra`
- [x] identity unaffected: `_session_id` (start|end|tool|model|in|out)
  identical for an extra-only difference; dataclass eq ignores extra
- [x] forward-compat: `cost_center=` preserved + re-emitted, **not
  interpreted** (no attribute created), other fields untouched
- [x] no injection: `"a=b c d"` value → one token, decodes back intact
- [x] malformed extra key dropped, not stored
- [x] `a ` amendment parsing unchanged (extra is `s `-line only)

## Decision-gate outcome (recorded)
- Byte-stable empty case **achieved** — the parse-and-warn fallback
  was NOT needed.
- Nuance recorded: `session_hash` hashes the raw line, so a line
  *with* an extra token naturally hashes differently from one
  without — that is correct (it is the join key for the exact
  written line). The load-bearing invariants are (a) lines with no
  extra are byte-identical ⇒ same `session_hash` ⇒ existing
  amendments unaffected, and (b) the cache/identity key
  `_session_id` is derived from immutable fields only ⇒ an
  extra-only difference never repartitions the cache. Both pinned.

## Docs
- [x] `docs/integration-contract.md` — extension point now "shipped
  (v2.75)"; hedge removed
- [x] `docs/PRD-ai-work-ledger.md` — payer:work-unit + v3.0-ROI
  through-line (shipped in the prior docs pass)
- [x] Roadmap entry + status/test count in `openspec/project.md`

## Gate
- [x] `pytest` green (1275 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
