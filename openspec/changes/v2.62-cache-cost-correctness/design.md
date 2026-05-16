# v2.62 — Cache-Aware Cost Correctness: Design

## Phase 1 — Audit (no code change; findings recorded here)

For each collector, determine from the actual payload/transcript
schema whether `input_tokens` includes cached tokens:

| Collector | Source field(s) | input incl. cache? | cache_write avail? |
|---|---|---|---|
| claude_code | `usage.input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` | Anthropic: input is **exclusive** of cache; cache_creation/read separate — verify on a real transcript | yes (already) |
| cursor | hook usage payload | TBD by audit | yes (already) |
| gemini_cli | `/quit`-style usage / transcript | TBD — the 1,022,341 vs 838,991 example is the test case | TBD |
| codex_app | rollout JSONL token fields | TBD | TBD |

The audit result is written back into this design as the
authoritative per-collector contract before any capture change.

## Phase 2 — Normalise at capture

Single invariant enforced in every collector:

> `input_tokens` = fresh input only. Cached input is **never** also in
> `input_tokens`; it is only in `cache_read` / `cache_write`.

Implementation: in each collector, immediately after reading raw
counts, if the audit found that collector's input is cache-inclusive,
subtract `cache_read (+ cache_write where applicable)` from
`input_tokens` (floor at 0) before constructing `AiSession`. A shared
helper keeps the rule in one place:

```
def normalise_input(raw_input, cache_read, cache_write, *, cache_inclusive: bool) -> int
```

Collectors whose input is already exclusive pass `cache_inclusive=False`
(no-op) — so a correct collector is provably unchanged.

## Phase 3 — Capture cache_write for Gemini/Codex

Extract the cache-creation field from the Gemini usage block / Codex
rollout token record when present; else `cache_write=None`.

## Tests (`tests/test_v262_cache_cost_correctness.py`)

1. Per-collector token-contract test: feed a fixture with known
   input/cache and assert the constructed `AiSession` honours the
   invariant (fresh-only input; cache in cache fields).
2. Double-count regression: a cache-inclusive fixture → cost does NOT
   bill the cached tokens at both 1.0× and 0.10×; equals hand-computed
   correct cost.
3. Gemini/Codex `cache_write` populated when the fixture provides it;
   `None` when absent (not `0`).
4. Already-exclusive collector → byte-identical cost to pre-change
   (no-op proof).
5. Composes with v2.61: a multi-model + cached session costs each
   segment with corrected cache semantics.

## Docs

`docs/PRD-ai-work-ledger.md` (the ledger/cost feature PRD) gains a
short "Token contract" subsection stating the fresh-input invariant
and the documented pre-v2.62 Gemini/Codex cache-write under-count.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap entry.
Data-correctness/bug-class; specced up front per the user's request.
