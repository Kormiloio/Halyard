# Spec: Struggle signals (surface only)

WHEN/THEN requirements. Subordinate to the v3.0 privacy contract:
counts/booleans only, no prompts/code/tool names, no new egress.

## R1 — Tool-error surfacing (universal capture)

- WHEN sessions in the window have `tool_calls` data, THEN
  `summarize_struggle` reports `tool_error_total = sum(tool_errors)`
  and `tool_error_rate = sum(tool_errors) / sum(tool_calls)`.
- WHEN the summed `tool_calls` over the window is 0 or no session has
  `tool_calls`, THEN `tool_error_rate` is None and
  `tool_error_total` is None (absent, never 0-by-default).
- WHEN tool-error data exists, THEN its trust label is `captured` and
  it is shown with no capture caveat.

## R2 — Rejection surfacing is availability-gated

- WHEN computing rejection stats, THEN only sessions with
  `interaction_data_available is True` are counted; all others are
  excluded from both numerator and denominator.
- WHEN at least one such session exists, THEN
  `rejection_rate = sum(rejected) / sum(rejected + accepted)` over only
  those sessions (None if that denominator is 0), and
  `rejection_covered` is the count of such sessions.
- WHEN no session in the window has
  `interaction_data_available is True`, THEN the entire rejection half
  is None and `rejection_covered == 0`.

## R3 — Honest coverage rendering (load-bearing)

- WHEN a surface shows rejection numbers AND `rejection_covered > 0`,
  THEN it MUST also show the coverage, e.g.
  `"rejections 12 (over 34 of 210 sessions; rest: not captured)"`.
- WHEN `rejection_covered == 0`, THEN the surface MUST render
  `"rejections: not captured"` (or equivalent) and MUST NOT render a
  bare `0` or a `0%` rejection rate.
- WHEN tool-error numbers are shown, THEN no capture caveat is attached
  (capture is universal).

## R4 — Outcome report

- WHEN `outcome report` runs AND a bucket has tool-call data, THEN the
  bucket prints a struggle sub-line with tool-error count and rate.
- WHEN a bucket has no tool-call data, THEN the bucket renders exactly
  as in v3.1 (no struggle line, no empty slot, no crash).
- WHEN a bucket has rejection-covered sessions, THEN the sub-line
  appends the rejection clause with its coverage per R3.

## R5 — Leverage panel parity (web + TUI)

- WHEN the Leverage panel renders (web or TUI) AND struggle data
  exists, THEN it shows one struggle line derived from the shared
  `summarize_struggle`, within the existing refresh budget.
- WHEN struggle data is absent, THEN both surfaces render exactly as in
  v3.1 (no struggle line).
- WHEN both surfaces render with the same sessions, THEN the tool-error
  rate and rejection figures they display are identical.

## R6 — No capture / schema / collector change

- WHEN v3.2 is implemented, THEN no file under
  `src/halyard/collectors/` is modified, no new log token is emitted,
  `db.py` schema and `_CREATE_SCHEMA_V1` are unchanged, and no new
  `AiSession` field is added.
- WHEN a session is parsed, THEN v3.2 reads only the pre-existing
  fields `tool_calls`, `tool_errors`, `accepted_suggestion_count`,
  `rejected_suggestion_count`, `interaction_data_available`.

## R7 — Invoice appendix unchanged

- WHEN the invoice evidence appendix renders, THEN it is byte-identical
  to v3.1 — struggle signals are internal and MUST NOT appear on a
  client-facing invoice.

## R8 — Privacy

- WHEN any struggle value is computed or rendered, THEN only integers,
  rates derived from integers, and the integer coverage counts appear —
  never a tool name, prompt, path, or any free text.
- WHEN the privacy fuzz suite runs, THEN seeded sensitive markers in
  free-text session fields never appear in any struggle surface.
