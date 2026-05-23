# v2.72 — Declarative field registry: Design

Status: **final.**

> Spec only — proposed. Verified against current `ai_log.py` (1029
> lines; 45 `kvs.append` writers, 45 matching parser `case` arms).

## Phase 0 — pin behaviour BEFORE refactoring (mandatory gate)

Lesson carried from v2.67/v2.71: never refactor a serialization path
without a behaviour pin first.

1. Write `tests/test_v272_round_trip.py` with a **property-based**
   round-trip (Hypothesis if available, else a broad hand-rolled
   matrix): for an `AiSession` populated with adversarial values for
   every field (commas, spaces, `=`, `%`, newlines-as-literals,
   unicode, None, 0, negative, very long), assert
   `from_log_line(to_log_line(s)) == s` for every serialized field,
   AND that `to_log_line(s)` is byte-identical before/after the
   refactor (golden corpus of real log lines committed as a fixture).
2. Capture a golden fixture from the existing code (current
   `to_log_line` output for a representative session set) and assert
   the refactor reproduces it byte-for-byte.
3. **Gate:** the pin must pass on the *unrefactored* code first. Only
   then does the registry land, and it must keep both green with zero
   diff to the golden corpus. If the registry cannot be expressed
   without changing any byte, stop and keep the manual code.

## The registry

A module-level ordered tuple in `ai_log.py`:

```python
@dataclass(frozen=True)
class FieldSpec:
    attr: str          # AiSession attribute name
    key: str           # on-wire key (usually == attr)
    kind: FieldKind    # selects the encode/decode pair + emptiness rule

# Ordered exactly as today's to_log_line emits (order is part of the
# byte-identical contract).
_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("project", "project", FieldKind.SAFE),
    FieldSpec("cache_read", "cache_read", FieldKind.INT),
    FieldSpec("tags", "tags", FieldKind.TAGS),
    FieldSpec("note", "note", FieldKind.FREETEXT),
    ...  # one line per existing optional key=value field
)
```

`FieldKind` enumerates the *existing* families already in the code —
no new behaviour:

| kind | encode | decode | emit-when |
|---|---|---|---|
| INT | `str(v)` | `int(v)` (suppress) | `v is not None` |
| FLOAT4 | `f"{v:.4f}"` | `float(v)` | `v is not None` |
| BOOL_LOWER | `str(v).lower()` | `== "true"` | per current rule |
| SAFE | `_safe_field` | raw | truthy |
| FREETEXT | `_encode_free_text` | `_decode_free_text` | truthy |
| TAGS | `,`-join `_encode_free_text` | split + `_decode_tag` | non-empty |
| BREAKDOWN | `_safe_breakdown` | raw | truthy |

The exact emit-when predicate per field is copied verbatim from
today's `if self.x is not None` / `if self.x:` guards — the registry
records which, it does not redesign it.

## Serializer

`to_log_line()` keeps the positional head
(`s start end tool model in out cost`) hand-written (unchanged), then:

```python
for spec in _FIELDS:
    val = getattr(self, spec.attr)
    token = _emit(spec, val)        # None if emit-when is false
    if token is not None:
        kvs.append(token)
```

## Parser

`_parse_line_result()` keeps positional parsing + the `s`/length
guards unchanged. The `match`/`case` tail becomes a dict lookup:

```python
_BY_KEY = {spec.key: spec for spec in _FIELDS}
...
spec = _BY_KEY.get(key)
if spec is not None:
    _apply(spec, session, value)   # decode + setattr, suppressing
                                   # ValueError exactly as today
```

Special-cased keys that are NOT simple attr setters (the v2.24
`branch:`-tag promotion, any computed/legacy alias) stay as explicit
code outside the registry loop — the registry is for the 1:1 fields
only, which is the large majority. The design will enumerate the
non-registry exceptions explicitly in tasks.md after an audit pass.

## What stays untouched (hard scope fence)

Positional head fields; `parse_amendment`/`apply_amendment`;
`_write_quarantine`; the v2.53 synthetic-telemetry guard;
`session_hash`; `_raw_hash`; `_iter_log_lines`; the
`from_log_line`/`parse_sessions`/`maybe_emit_milestones` public API
signatures. No call site outside `ai_log.py` changes.

## Tests

- `test_v272_round_trip.py` — the Phase 0 pin (property + golden
  corpus), kept as a permanent regression.
- A registry-coverage test: every optional `AiSession` field is
  either in `_FIELDS` or on an explicit allow-list of non-registry
  exceptions — so a future added field can't silently bypass both.
- The full existing suite must stay green with zero expected-output
  edits (proof of byte-identical behaviour).

## Decision gate (restated)

Net effect must be: fewer lines AND one edit-site per new field AND
zero behaviour diff. If any of those fails, the changeset is
abandoned and `ai_log.py` stays as-is — that is an acceptable
outcome, recorded, not a failure.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry. Refactor-class changeset — full spec, behaviour-pinned.
