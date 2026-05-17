# v2.75 — Extensible log contract: Tasks

Status: **proposed (spec only, not started).** Closes the v2.71
silent-drop gap; makes the line format extensible so consumers
(incl. Halyard-Enterprise) extend it without forking the parser.

## Build
- [ ] `AiSession.extra: dict[str,str]` (default factory;
  `compare=False` — must not affect equality / `_session_id` /
  `session_hash`)
- [ ] Parser `case _:` — preserve unknown `key=value` verbatim
  (percent→`_decode_free_text`, else raw); reject malformed keys;
  known fields still matched first (no shadowing)
- [ ] `to_log_line` re-emits `extra` sorted-by-key, after known
  fields, via `_encode_free_text` (injection-safe, byte-stable)

## Hard invariants (tests, `tests/test_v275_extensible_log.py`)
- [ ] round-trip lossless incl. space/`=`/`%`/unicode/comma values
- [ ] `extra=={}` ⇒ byte-identical to pre-v2.75 (golden corpus, zero
  existing-output diff)
- [ ] no shadowing: known-field keys never land in `extra`
- [ ] identity unaffected: `extra`-only difference ⇒ same
  `_session_id` / `session_hash` (cache + amendment join intact)
- [ ] forward-compat: Enterprise-style `cost_center=` token
  preserved + re-emitted, **not interpreted** by OSS
- [ ] no injection: `"a=b c d"` value round-trips as one value
- [ ] quarantine + `a ` amendment paths unchanged

## Decision gate
- [ ] If byte-stable empty-case round-trip is not achievable, reduce
  to parse-and-warn (doctor surfaces unknown tokens) instead of
  dropping — record the decision, do not risk the contract

## Docs (separate pass, tracked here for visibility)
- [ ] `docs/integration-contract.md` — declare the `ai-sessions.log`
  line grammar + `--json` schema a stable, versioned, backward
  -compatible integration surface; `extra` is the documented
  extension point
- [ ] Neutral attribution semantics + v3.0-as-ROI-through-line
  wording in `docs/PRD-ai-work-ledger.md` (no data-model change)
- [ ] Roadmap entry + status/test count in `openspec/project.md`

## Gate
- [ ] `pytest` green
- [ ] `ruff check` + `ruff format --check` clean
- [ ] `mypy src/` clean
