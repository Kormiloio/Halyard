# Design: v3.2 — Struggle signals (surface only)

## Phase-0 collector-coverage audit (complete, 2026-05-18)

Grepped all four collectors in `src/halyard/collectors/`:

| Field                        | claude_code | cursor | gemini_cli | codex_app |
|------------------------------|:-----------:|:------:|:----------:|:---------:|
| `tool_calls`                 | yes         | yes    | yes        | yes       |
| `tool_errors`                | yes         | yes    | yes        | yes       |
| `accepted_suggestion_count`  | no          | yes    | no         | no        |
| `rejected_suggestion_count`  | no          | yes    | no         | no        |
| `interaction_data_available` | (unset)     | set    | (unset)    | (unset)   |

- `tool_errors`/`tool_calls`: **universal** — surface unconditionally,
  trust `captured`.
- `accepted/rejected_suggestion_count`: **Cursor-only**. The honest
  primitive already exists: `AiSession.interaction_data_available`
  (v2.32). Cursor sets it; the others leave it unset/None. That field
  is the rejection denominator gate — no new field needed.
- No collector references `mcp` — MCP inventory stays out of scope.

Conclusion: no spike, no capture work, no schema work. This is purely a
read-and-render change over audited, already-parsed fields.

## Schema decision: no schema change

The surfaces (`outcome_report`, `leverage.summarize`, the panels) all
operate on the parsed `list[AiSession]` from the plain-text log, not on
the SQLite cache. `db.py`'s `sessions` table has `tool_errors` but not
the suggestion counts — irrelevant here, because nothing in v3.2 reads
the cache for these. **No migration, no `_CREATE_SCHEMA_V1` change.**
A test pins that `db.py` is untouched.

## Approach

Mirror v3.1's parity mechanism exactly. Add a struggle summary to the
shared `leverage` module so web and TUI cannot diverge:

```
@dataclass(frozen=True)
class StruggleSummary:
    tool_error_total: int | None        # sum over window; None if no tool_calls anywhere
    tool_error_rate: float | None       # errors / tool_calls, None if denom 0
    rejection_total: int | None         # sum over interaction-captured sessions only
    rejection_rate: float | None        # rejected / (accepted+rejected), captured-only
    rejection_covered: int              # # sessions counted toward rejection stats
    rejection_total_sessions: int       # # sessions in window (for the coverage string)
```

`summarize_struggle(sessions, now)` (same 30-day window as
`leverage.summarize`):

- Tool errors: denom = sum of `tool_calls` over sessions where
  `tool_calls` is not None; numer = sum of `tool_errors`. Rate is None
  when denom is 0 (never divide-by-zero; absent ≠ 0).
- Rejections: consider only sessions with
  `interaction_data_available is True`. `rejection_covered` = that
  count; `rejection_rate = sum(rejected) / sum(rejected+accepted)` over
  just those, None if that denom is 0. If `rejection_covered == 0` the
  whole rejection half is None and surfaces print "not captured".

Report (`outcome_report` / `OutcomeBucket`): add
`tool_error_total`, `tool_error_rate`, and an optional rejection
triple computed per bucket with the same availability gate. Absent →
fields None → `cli_outcome` prints no struggle sub-line (v3.1-identical).

Surfaces:

- `cli_outcome` report: a `└ struggle:` sub-line, only when
  `tool_error_total is not None`. Rejection clause appended only when
  `rejection_covered > 0`, always with the coverage count.
- Web `_leverage_panel`: a `.leverage-struggle` line (reuse the muted
  style), only when data exists.
- TUI `LeveragePane`: the same numbers via the shared summary — parity
  asserted by a test (web string ⊇ the rendered TUI number).
- Invoice appendix: **unchanged** — struggle is an internal signal;
  adding it to a client invoice is a misfeature. Explicit non-goal.

## Honest-labelling rule (the load-bearing decision)

The failure mode to avoid: a user whose sessions are mostly
claude_code/gemini/codex sees "rejections: 0" and reads "the AI is
never wrong", when the truth is "rejections were never captured for
those tools". Mitigation, enforced by spec + tests:

- Rejection numbers are **always** rendered with their coverage:
  `"rejections 12 (over 34 of 210 sessions; rest: not captured)"`.
- When `rejection_covered == 0`: render literally
  `"rejections: not captured (no interaction-aware collector)"` — never
  a bare `0`.
- Tool-error stats carry no such caveat (universal capture) and are
  shown plainly.

## Alternatives considered

- **Add a per-collector `rejection_capture_supported` flag.** Rejected:
  `interaction_data_available` already encodes exactly this per session
  and is the v2.32-blessed primitive. A new flag is redundant.
- **Backfill rejections for the other collectors now.** That is the
  out-of-scope cross-collector work — real hook/parsing changes per
  tool, deferred to its own changeset. v3.2 must not grow into it.
- **Put struggle on the invoice appendix.** Rejected: invoices are
  client-facing; internal thrash metrics there invite
  misinterpretation and scope creep. Internal surfaces only.

## Risks

| Risk | Mitigation |
|---|---|
| Misread Cursor-only rejections as global | Mandatory coverage string; never bare 0 (spec R3, tests) |
| Divide-by-zero on rate | Rate is None when denominator 0; surfaces omit the clause |
| Surface drift web vs TUI | Single `summarize_struggle`; parity test |
| Scope creep into collector work | Success criterion 4: no `collectors/` diff; out-of-scope is explicit |
