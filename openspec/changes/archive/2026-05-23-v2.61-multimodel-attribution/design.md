# v2.61 — Multi-Model Session Attribution: Design

## Encoding

Reuse the `model_breakdown` token; generalise its grammar:

```
model_breakdown = seg ( "|" seg )*
seg             = model ":" in "/" out "/" cr "/" cw
```

e.g. `model_breakdown=gemini-3-flash-preview:1004686/11254/822925/0|gemini-3.1-pro-preview:228932/3375/116420/0`

- Values are ints; `_safe_field` already escapes the token.
- **Back-compat parse:** a segment with no `/` (old `model:count`
  form) is read as count-only → no per-model usage → costed via the
  legacy single-model path. Lines with no `model_breakdown` are
  unchanged.
- `session.model` = the segment with the greatest cost share
  (computed at write time); ties broken by token volume then name.

## Cost

`pricing.calculate_cost` (or a thin `calculate_session_cost(session)`
wrapper, TBD at build) becomes:

```
if session has a usage-form model_breakdown:
    cost = sum(calculate_cost(m, i, o, cr, cw) for each segment)
else:
    cost = calculate_cost(session.model, input, output, cache_read, cache_write)  # unchanged
```

Session-level `input_tokens/output_tokens/cache_*` remain the totals
(sum of segments) so existing token consumers are unaffected.

## Rollups

`usage._model_buckets`, `mcp_server._cost_by_model`, and the dashboard
model-breakdown table currently do `bucket[session.model] += …`.
Introduce one shared helper:

```
def iter_model_usage(session) -> Iterable[tuple[model, in, out, cr, cw, cost]]
```

- breakdown present → yield one tuple per segment
- else → yield a single tuple from `session.model` + totals

Every per-model rollup iterates this instead of keying `session.model`
directly. One seam, three consumers fixed, single-model path identical.

## Collectors

Each collector already walks a transcript/usage stream that carries
per-event model. Tally per-model `(in,out,cr,cw)` and emit the
breakdown when ≥2 distinct models; else leave `model` as today and
`model_breakdown=None`.

- Claude Code — upgrade v2.60's per-model tally to the usage grammar.
- Cursor, Codex — add the tally (new).
- Gemini — replace the count-only breakdown with the usage grammar.

## Tests (`tests/test_v261_multimodel_attribution.py`)

1. Usage-form breakdown parses; cost = Σ per-model cost (assert vs
   hand-computed using the pricing table).
2. `session.model` = highest-cost segment.
3. Legacy `model:count` breakdown → costed by single-model path
   (back-compat), no crash.
4. No breakdown → byte-identical behaviour to today (regression).
5. `iter_model_usage` yields per-segment for multi-model and a single
   tuple otherwise; `_cost_by_model` / usage buckets attribute
   correctly for a 3-model session.
6. Round-trip: write → `parse_sessions` → equal session.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap entry.
Data-correctness/bug-class — specced up front at the user's request.
