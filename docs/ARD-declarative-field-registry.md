# ARD: Declarative Field Registry for AiSession Serialization

**Status:** Final
**Date:** May 22, 2026
**Related PRD:** `docs/PRD-halyard.md`
**OpenSpec change:** `openspec/changes/v2.72-field-registry/`

---

## Architecture Decision

Refactor the `AiSession` serialization and parsing logic in `ai_log.py` to use a
single ordered declarative registry (`_FIELDS`). This registry contains
`FieldSpec` records that define the mapping between `AiSession` attributes,
on-wire keys, and codec behaviors.

Both `to_log_line()` (the writer) and `_parse_line_result()` (the parser) iterate
over this shared registry to handle the 45+ optional `key=value` fields.

## Context

Previously, `ai_log.py` managed optional fields through two hand-maintained
blocks of code:

1.  A long sequence of `if self.field: kvs.append(...)` checks in `to_log_line()`.
2.  A matching `match key: case "key": self.field = ...` block in `_parse_line_result()`.

Maintaining these two blocks in byte-for-byte symmetry was error-prone. The
v2.71 `tags` corruption bug was caused by an asymmetry where the writer and
parser disagreed on encoding/decoding rules. As the number of metadata fields
grew beyond 40, the risk of drift became a significant technical debt.

## Constraints

- **Byte-identical output:** Newly written log lines must be identical to those
  produced by the previous implementation for the same data.
- **Backward compatibility:** The parser must remain able to read every line
  ever written by an older version of Halyard.
- **Forward compatibility:** Unknown tokens (passthrough) must be preserved
  verbatim (v2.75 contract).
- **Performance:** Serialization and parsing must remain O(fields) and
  single-pass.

## Components

### FieldKind (Enum)

Defines the codec family for a field:
- `SAFE_FIELD`: String sanitized via `_safe_field`.
- `INT`: Integer with `ValueError` suppression.
- `FLOAT_4`: Float rounded to 4 decimal places.
- `BOOL_LOWER`: Boolean rendered as `true`/`false`.
- `TOKENS_AVAILABLE`: Special boolean (omitted if true, `false` if false).
- `BILLING`: Special string (omitted if "api").
- `TAGS`: List of strings, joined by `,`, percent-encoded.
- `FREE_TEXT`: String percent-encoded via `_encode_free_text`.
- `BREAKDOWN`: String sanitized via `_safe_breakdown` (no length cap).

### FieldSpec (Dataclass)

A frozen record mapping an `AiSession` attribute to its wire key and `FieldKind`.

### Registry (_FIELDS)

A tuple of `FieldSpec` objects. The order in this tuple defines the emission
order in the log line, which is part of the byte-identical contract.

## Verification

Stability is verified by `tests/test_v272_round_trip.py`, which uses
**property-based testing** (Hypothesis) to ensure that:
1.  `from_log_line(to_log_line(session)) == session` for all valid field values.
2.  `to_log_line(from_log_line(line)) == line` for a golden corpus of complex lines.

## Benefits

- **Eliminates Asymmetry:** The writer and parser read from the same source of
  truth.
- **Reduced Churn:** Adding a new field is now a single-line change in the
  registry.
- **Improved Readability:** `ai_log.py` is reduced by ~100 lines of repetitive
  boilerplate.
- **Type Safety:** Codec behaviors are explicitly typed via `FieldKind`.

## Consequences

- Internal refactor only; zero impact on end-users or log format.
- Future field additions must adhere to the registry pattern.
- One-off exceptions (like legacy `branch:` tag promotion) are still handled
  outside the main loop but are clearly isolated.
