# v2.75 — Extensible log contract: Design

> Spec only. Verified against current `ai_log.py`:
> `_parse_line_result` `match k:` (~:698) has no `case _:`;
> `to_log_line` emits only known fields. Unknown `s `-line tokens are
> dropped and never re-emitted.

## Schema

`AiSession` gains:

```python
extra: dict[str, str] = field(default_factory=dict)
```

`compare=False` (like `_raw_hash`) — `extra` must not change equality
/ hashing semantics or the content-addressed session id (the cache
key and amendment join key stay derived from immutable identity
fields only; an Enterprise `cost_center=` token must NOT repartition
the cache or break amendment matching).

## Parser

Add a terminal `case _:` to the `match k:` block:

```python
case _:
    # Unknown token from a newer Halyard / an extending consumer
    # (e.g. Halyard-Enterprise). Preserve verbatim so the line
    # round-trips losslessly instead of silently dropping data.
    session.extra[k] = _decode_free_text(v) if "%" in v else v
```

- Placed last; every known key still matched first → **no shadowing**
  (a token named like a known field never reaches `extra`).
- Key constraint: only accept `k` matching the existing token-key
  shape (same `[A-Za-z0-9_]`-ish rule the writer guarantees);
  malformed keys are ignored, not stored, so `extra` can't become a
  junk sink from a corrupt line.
- Decode rule mirrors the established free-text convention (percent
  → `_decode_free_text`; else raw) so an Enterprise writer using the
  standard `_encode_free_text` round-trips exactly.

## Serializer

In `to_log_line`, after all known-field emission, before the line is
returned:

```python
for k in sorted(self.extra):
    kvs.append(f"{k}={_encode_free_text(self.extra[k])}")
```

- Sorted by key → deterministic, stable output (byte-stable
  round-trip; golden tests don't flap).
- Emitted **after** known fields → the known prefix is byte-identical
  to pre-v2.75 for any session with `extra == {}`.
- Re-encoded with `_encode_free_text` → an unknown value containing
  spaces/`=`/`%` can never forge record delimiters or extra tokens
  (same injection guard as every other free-text field).

## Hard invariants (test-pinned)

1. **Round-trip lossless:** `from_log_line(to_log_line(s)) == s` for a
   session carrying arbitrary `extra` (incl. values with spaces, `=`,
   `%`, unicode, commas).
2. **Byte-stable for empty extra:** a session with `extra == {}`
   serializes byte-identically to pre-v2.75 (golden corpus; no
   existing test output changes).
3. **No shadowing:** a line containing `project=` (a known field)
   never lands in `extra`; reserved keys always win.
4. **Identity unaffected:** two sessions differing only in `extra`
   produce the **same** content-addressed `_session_id` /
   `session_hash` → cache + amendment join unaffected.
5. **Forward-compat:** an old fixture line without unknown tokens
   parses with `extra == {}` (no regression); a line with an
   Enterprise-style `cost_center=alpha` token parses, preserves, and
   re-emits it unchanged — **without OSS interpreting it**.
6. **No injection:** an `extra` value `"a=b c d"` round-trips as one
   value, never splits the record or spoofs a known token.

## Tests (`tests/test_v275_extensible_log.py`)

Cases 1–6 above, plus: quarantine path unaffected (a malformed line
is still quarantined, not absorbed into `extra`); amendment line
(`a `) parsing unchanged (`extra` is `s `-line only).

## Decision gate

If preserving + re-emitting unknown tokens cannot be done **byte
-stably for the empty case** (no diff to the golden corpus), the
change is reduced to *parse-and-warn* (surface unknown tokens via
`doctor` instead of dropping) rather than risking the round-trip
contract. Recorded, not forced.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry. Data-integrity changeset; ships with a docs pass (integration
contract + neutral attribution) tracked alongside.
