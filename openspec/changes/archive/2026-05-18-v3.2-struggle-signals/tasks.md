# Tasks

Implementation checklist for v3.2 — Struggle signals (surface only).

## 0. Prerequisites

- [x] 0.1 v3.0 + v3.1 complete.
- [x] 0.2 Phase-0 collector-coverage audit done (2026-05-18) and
  recorded in `design.md`: `tool_errors`/`tool_calls` universal;
  `accepted/rejected_suggestion_count` Cursor-only;
  `interaction_data_available` is the rejection gate; no MCP capture.
  No spike outstanding — surface-only over audited fields.

## 1. Shared summary (single source for web + TUI)

- [x] 1.1 `StruggleSummary` + `struggle_signals()` (caller-sliced) +
  `summarize_struggle(sessions, now)` (30-day window) + shared
  `render_rejection_phrase()` in `leverage.py`.
- [x] 1.2 Tool-error math: `tool_error_total` None when no session has
  `tool_calls`; `tool_error_rate` None when summed `tool_calls` == 0
  (never 0-default, never divide-by-zero).
- [x] 1.3 Rejection math gated on `interaction_data_available is True`;
  exposes `rejection_covered` + `rejection_total_sessions`; whole half
  None when covered == 0.

## 2. Outcome report

- [x] 2.1 `OutcomeBucket.struggle: StruggleSummary | None`
  (TYPE_CHECKING import, no runtime cycle); computed per bucket
  (incl. "Not synced"); None for an empty bucket.
- [x] 2.2 `cli_outcome` prints a `└ struggle:` sub-line only when
  `tool_error_total is not None`; rejection clause via
  `render_rejection_phrase` (R3); absent path byte-identical to v3.1.

## 3. Leverage panel (parity)

- [x] 3.1 Web `_leverage_panel`: `.leverage-struggle` line (+CSS,
  muted) only when tool-error data exists.
- [x] 3.2 TUI `LeveragePane`: same numbers via the shared
  `summarize_struggle` + `render_rejection_phrase`.
- [x] 3.3 R3 coverage rendering centralized in
  `render_rejection_phrase` — never a bare 0 in either surface.

## 4. Tests (17, ≥15 required)

- [x] 4.1 tool-error rate / denom-0→None / no-tool_calls→None.
- [x] 4.2 rejection gate: mixed Cursor + non-Cursor → denom is
  captured-only; covered==0 → all None; 0/(0+0)→None.
- [x] 4.3 R3 honesty: not-captured phrase has no "0"; coverage string
  present when covered>0; genuine-zero still shows coverage not bare 0.
- [x] 4.4 report per-bucket struggle; empty bucket → None; no-tool
  data → `tool_error_total` None (cli omits line).
- [x] 4.5 web↔TUI parity (identical figure + phrase); absent →
  no `leverage-struggle`, no "tool errors" in TUI.
- [x] 4.6 R6: required pre-existing fields present; no `struggle*`
  field on `AiSession`; no `struggle` token in `to_log_line()`.
- [x] 4.7 R7: `_render_pr_refs_subsection` identical with/without
  struggle data; no "struggle" in invoice output.
- [x] 4.8 privacy: markers in note/resume_command never reach the
  leverage panel, report, or TUI struggle surface.

## 5. Spec sync (close-out, same session as code)

- [x] 5.1 Ticked incrementally as items landed (not batched).
- [x] 5.2 No implementation deviation from `design.md` (the
  no-schema / availability-gate / shared-phrase approach shipped as
  designed). `struggle_signals` was split out from
  `summarize_struggle` so per-bucket report reuse needs no 30-day
  window — a refinement, not a deviation.
- [x] 5.3 Roadmap entry 56 added to `openspec/project.md` with final
  test count; deferred siblings noted.
- [x] 5.4 Archived to
  `openspec/changes/archive/2026-05-18-v3.2-struggle-signals/`.
