# v2.72 — Declarative field registry for AiSession serialization

> Spec only — proposed, not started. A deliberate refactor, not
> hardening. Architecture is stable; this is optional simplification
> whose value must clear its churn cost before any code moves.

## Why

`ai_log.py` (1029 lines) declares every optional `AiSession` field's
wire handling in **two** hand-maintained places:

- `to_log_line()` — 45 `kvs.append(f"key={encode(self.attr)}")` lines.
- `_parse_line_result()` — 45 matching `case "key":` arms.

The two lists must stay byte-for-byte symmetric (same key name, same
encoder/decoder pairing, same type coercion). They are kept in sync by
hand. The v2.71 `tags` corruption bug was exactly this class: the
writer used `_safe_field` while the reader split on `,` — a
writer/parser asymmetry that no single place owned. Every new field
is two coordinated edits with no structural guard that they agree.

This is not a correctness emergency (v2.71 added the round-trip tests
that would now catch such drift) — it is a maintainability and
defect-class-elimination proposal.

## What changes

Introduce a single ordered **field registry**: a list of `FieldSpec`
records, one per optional key=value field, each owning:

- the `AiSession` attribute name,
- the on-wire key,
- a `kind` (int / float4 / bool-lower / safe-field / free-text /
  tags / breakdown — the existing encode/decode families),
- and therefore exactly one encode fn and one decode fn, paired.

`to_log_line()` and the parser both **iterate the same registry**.
Adding a field becomes one `FieldSpec` line; the writer and parser
can no longer disagree because they read from one source.

Out of scope of the change: the 8 positional head fields
(`s start end tool model in out cost`), amendment folding, quarantine,
synthetic guard, hashing — all unchanged. This touches only the
optional key=value tail, which is where the asymmetry risk and ~90 of
the ~1029 lines live.

## Why this, not Pydantic

Pydantic (de)serializes to JSON/dict, not to the bespoke
`s … key=value` plain-text contract that is Halyard's published
format and "plain-text-first" mission. A Pydantic migration would
**not** replace `to_log_line`/`from_log_line` — the custom format
codec stays hand-written; Pydantic would only restate the field
declarations and add validator boilerplate on the hottest path
(every collector write + every read). The registry captures the real
benefit (one source of truth, asymmetry impossible) at a fraction of
the churn and with zero format/mission change. A Pydantic boundary
model remains a clean *later* option if input validation ever needs
it — it does not today (validation is already at the collector edge).

## Constraints honored

- **Byte-identical output.** Existing logs and newly written lines
  are unchanged to the byte. A property-based round-trip test is
  written **first** and pins this before any refactor.
- **No format/schema change. No mission change.** Still plain-text,
  still streamed, still backward/forward compatible.
- **Performance neutral.** Registry iteration is O(fields), same as
  the current straight-line code; parsing stays single-pass.

## Non-goals

- Pydantic / JSON schema adoption (explicitly deferred; see above).
- Touching positional fields, amendments, quarantine, hashing.
- Any change to the wire format, encoders, or field set.

## Decision gate

If, once the round-trip test exists, the registry does not
*measurably* reduce net complexity (lines + the count of places a
new field must be edited) without behaviour change, **do not ship
it** — the manual code is acceptable and stable. This proposal is
explicitly cancellable at that gate.
