# v2.75 — Extensible log contract (unknown-token preservation)

> Spec only — proposed. Dual-justified: closes the v2.71
> documented-not-built silent-data-loss gap **and** is the concrete
> forward-compat enabler for Halyard-Enterprise (private strategy).

## Why

`_parse_line_result`'s `match k:` has **no `case _:`** — an
unrecognized `key=value` token on an `s ` line is silently dropped,
and `to_log_line` only re-emits known fields, so any unknown token is
lost on the first parse/rewrite. Two consequences:

1. **OSS integrity (v2.71 gap):** a token written by a *newer*
   Halyard that an *older* parser doesn't know is silently discarded
   — quiet data loss, no signal. v2.71 documented this as
   not-built; this builds it.
2. **Ecosystem / Enterprise forward-compat:** any consumer that
   extends the line (e.g. Halyard-Enterprise adding `cost_center=`,
   `org_unit=`, `roi_ref=`) currently forces a **fork of the OSS
   parser**. Preserve-and-re-emit makes the format *extensible* —
   the Enterprise layer (and any third-party tool) becomes additive,
   not a divergent rewrite. This is the single highest-leverage
   forward-compat lever and it is on-mission (data-integrity), not an
   enterprise feature in OSS.

## What changes

- Add `extra: dict[str, str]` to `AiSession` (default empty).
- Parser: a `case _:` captures any unrecognized `key=value` into
  `extra` verbatim (value `_decode_free_text`-decoded only if it
  carries a `%`; otherwise stored raw — no lossy transform).
- `to_log_line`: re-emit `extra` tokens, deterministically ordered
  (sorted by key), **after** all known fields, so a known→unknown→
  known round-trip is byte-stable for the known part and lossless
  for the unknown part.
- Reserved/structural keys can never be shadowed: a token whose key
  collides with a known field is handled by the known `case`, never
  routed to `extra` (no override path — security/forgery guard
  preserved).

## Constraints honored

- **Backward compatible.** Old lines (no unknown tokens) →
  `extra == {}`, byte-identical output. Older parsers still ignore
  the new tokens (same tolerance we now add).
- **No new captured data in OSS.** OSS writes nothing into `extra`;
  it only *preserves* what another writer put there. The capture
  surface is unchanged.
- **Trust/quarantine/synthetic guards unchanged.** `extra` is opaque
  passthrough; it is never interpreted, scored, or trusted by OSS
  surfaces. Amendment/quarantine/synthetic paths untouched.
- **No security regression.** Unknown tokens are still
  `_safe_field`-class constrained on emit; cannot inject record
  delimiters; cannot shadow known fields.

## Non-goals

- OSS does not *interpret* `extra` (no `cost_center` semantics in
  OSS — that's Enterprise).
- Not a schema/versioning rev of the line format itself (the grammar
  is unchanged; this is additive tolerance).
- The published-contract doc + neutral-attribution wording ship
  alongside as a docs pass, tracked separately, not in this
  changeset's code scope.
