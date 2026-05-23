# v2.62 — Cache-Aware Cost Correctness: Design

## Phase 1 — Audit (COMPLETE 2026-05-16; no code change)

Authoritative per-collector token contract, derived from the actual
capture code + each tool's documented usage schema:

| Collector | Source field(s) | input incl. cache at source? | normalised at capture? | cache_write avail? |
|---|---|---|---|---|
| claude_code | `usage.input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` (payload + transcript, same Anthropic schema) | **No — exclusive** (Anthropic Messages API contract: `input_tokens` excludes cache; read/creation are disjoint counts) | n/a (already exclusive) | **Yes** — `cache_creation_input_tokens` captured (`claude_code.py:127,508`) |
| cursor | stop payload, "structurally identical to Claude Code's Stop payload" — same Anthropic-shaped `usage` block | **No — exclusive** (Anthropic pass-through schema) | n/a (already exclusive) | **Yes** — `cache_creation_input_tokens` captured (`cursor.py:103`). Note: cost is always `0.0` (`billing="credits"`) so $ is moot; invariant matters only for token rollups |
| gemini_cli | hook: `usageMetadata.promptTokenCount` / `cachedContentTokenCount`; history: `tokens.input` / `tokens.cached` | **Yes — gross** (`promptTokenCount`/`tokens.input` is total prompt *including* cached subset) | **Yes, already** — hook path `net_input = max(0, prompt − cache)` (`gemini_cli.py:234`); history path `s.input_tokens += max(0, inp − cached)` (`gemini_history.py:151`). The 1,022,341 vs 838,991 example → net **183,350**, matching the spec scenario exactly | **No** — Gemini exposes `cachedContentTokenCount` (read) only; no cache-creation field anywhere in payload or history. Correctly stays `None` |
| codex_app | rollout JSONL `info.total_token_usage`: `input_tokens` / `cached_input_tokens` / `output_tokens` / `total_tokens` | **Yes — gross** (`input_tokens` is total input incl. cached subset) | **Yes, already** — `net_input = max(0, total_input − cached_input)` (`codex_app.py:205`). o-series fallback (output==0) uses `total_tokens` proxy, cost 0 anyway | **No** — `total_token_usage` exposes `cached_input_tokens` (read) only; no cache-creation field. Correctly stays `None` |

### Audit conclusion (material — rescopes the change)

1. **The suspected double-count does not exist.** Every collector
   already emits fresh-only `input_tokens`: claude/cursor because the
   Anthropic schema is natively exclusive; gemini/codex because both
   already subtract the cached subset before constructing `AiSession`.
   No line is currently mispriced on this axis.

2. **`cache_write` for Gemini/Codex is structurally unavailable, not
   dropped.** Neither tool's payload/transcript exposes a
   cache-creation token field — only Anthropic (claude/cursor) does,
   and both already capture it. So "capture cache_write for
   Gemini/Codex" resolves to "document why it is `None`" (the
   "unavailable is not zero" rule is already correctly applied).

3. **Therefore the value of v2.62 is regression-proofing + an
   explicit contract, not a behavioural fix.** The risk was real
   (an unverified double-count for a trust-first tool) but the
   verification clears it. Phase 2's `normalise_input` becomes a
   *codification* of an invariant already met (no observable change;
   no-op for claude/cursor, equals current `max(0, …)` math for
   gemini/codex). Phase 3 becomes a documentation task. The durable
   deliverable is the per-collector regression test that locks the
   invariant so a future collector/schema change cannot silently
   reintroduce the double-count.

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
