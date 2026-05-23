# v2.70 — TUI ↔ web dashboard parity: Design

> Spec only — proposed. Awaiting alignment before code.

## Audit (data builders all exist — TUI only renders)

| Web panel | Data source (reuse) | TUI today |
|---|---|---|
| Moat: cost-by-client | `moat.cost_by_client(sessions)` | absent |
| Moat: attribution confidence | `attribution.attribution_confidence(s)` | absent |
| Moat: leakage funnel | `moat.leakage(unattributed_log)` | absent |
| Moat: per-project billable evidence | `build_ai_report` + human-time + outcomes | absent |
| Leverage "did it ship?" | inline in `dashboard._leverage_panel` | absent |
| Usage stats | `build_usage_analytics` | present (v2.64 `UsagePane`) |

No new builder is needed. One small refactor: the leverage % +
buckets math is inline in `dashboard.py:1569 _leverage_panel`. Factor
it into `leverage.summarize(sessions, now) -> LeverageSummary`
(new tiny module or a function on an existing one); the web panel and
the new TUI pane both call it — single source of truth, no divergence.

## New TUI widgets

`tui/widgets/moat_pane.py` — `MoatPane(Static)` with
`render_sessions(sessions, project_dir, now)`:

- **Cost by client:** table rows `client  $spend  Δ vs prev` from
  `cost_by_client`; compact in-row bar.
- **Attribution confidence:** one mixed-bar line (timer/mapped/toml/
  auto/none %) from `attribution_confidence` over the sessions.
- **Leakage:** rows `remote  $adrift  → halyard link-repo …` from
  `moat.leakage`; the exact fix string (propose, never run).
- **Billable evidence:** per project `human Xh · AI $Y · shipped a/b ·
  conf Z` (reuses `build_ai_report` buckets + human-time +
  `pr_state`).

`tui/widgets/leverage_pane.py` — `LeveragePane(Static)`:
`leverage.summarize(...)` → "Shipped N% · merged a / open b /
none c", same buckets as the web Leverage panel.

Both render to `self.last_rendered_text` then `self.update(...)` —
exactly the `UsagePane` pattern (unit-testable without Pilot).

## App wiring (`tui/app.py`)

- `compose()` yields `MoatPane(id="moat-pane")` and
  `LeveragePane(id="leverage-pane")`.
- `refresh_views()` calls their `render_sessions(...)` with the
  active filtered session set + `store.log_path.parent` +
  `generated_at`, like the other panes.
- A binding to focus/scroll the moat pane (reuse the existing
  selection/scroll actions; no new modal).
- Escaped text only (v2.38 Rich-markup-injection invariant —
  `rich.markup.escape` on any model/remote/client string, as the
  other panes already do).

## Shared leverage calc

`leverage.py`:

```python
@dataclass(frozen=True)
class LeverageSummary:
    total: int; merged: int; open_: int; none: int; pct: int
def summarize(sessions: list[AiSession], now: datetime) -> LeverageSummary
```

`dashboard._leverage_panel` is refactored to call `summarize()` and
only format HTML from it (behaviour-identical — pinned by the
existing dashboard leverage test).

## Tests (`tests/test_v270_tui_parity.py`)

1. `MoatPane.render_sessions` over a fixture: text contains the
   client, the $ spend, the leakage remote + its `link-repo` fix, and
   the confidence mix — and **no** Rich markup leaks (escape proof).
2. `LeveragePane` text shows the shipped % and merged/open/none
   counts matching `leverage.summarize`.
3. `leverage.summarize` parity: the web `_leverage_panel` and the TUI
   pane derive identical numbers from the same sessions (single
   -source-of-truth proof; dashboard leverage golden unchanged).
4. Empty/no-data: panes render a clean empty state, no exception.
5. Confidence/trust labels present in the moat pane (not flattened).
6. App wiring smoke: `compose()` includes the two pane ids;
   `refresh_views()` populates `last_rendered_text` (store-layer
   test, no Pilot).

## Docs & policy

- `openspec/project.md` "Deferred or gated" TUI bullet: generalise
  the v2.64 carve-out — record that v2.70 lifts the TUI-deferral for
  the moat/leverage parity panes by owner decision (info parity,
  testable-text layer; the broader Pilot-harness deferral stands for
  untouched widgets).
- `docs/PRD-local-activity-dashboard.md`: note TUI now mirrors the
  moat + leverage story (information parity).

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry. Feature changeset + a documented policy lift — full spec.
