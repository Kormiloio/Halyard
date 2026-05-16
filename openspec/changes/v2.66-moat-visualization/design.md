# v2.66 — Moat Visualization Surface: Design

## Data layer (`usage.py` / new `moat.py`)

All derivable from the already-selected aggregate session set; no new
capture. Add a small `src/halyard/moat.py` so dashboard rendering stays
thin and the rollups are unit-testable in isolation:

```python
@dataclass(frozen=True)
class ClientCostPoint:      # for #1
    period: date            # week bucket
    project: str            # client:project (or "(adrift)")
    cost_usd: float

@dataclass(frozen=True)
class ConfidencePoint:      # for #2
    period: date
    band: AttributionConfidence   # from halyard.attribution
    sessions: int

@dataclass(frozen=True)
class ProjectEvidence:      # for #3
    project: str
    human_minutes: int          # build_human_time_report per project
    ai_cost_usd: float
    sessions: int
    shipped: int                # pr_state == merged
    in_flight: int              # open
    abandoned: int              # closed
    no_pr: int                  # none / unsynced
    confidence: AttributionConfidence   # dominant band for the project

@dataclass(frozen=True)
class LeakRow:              # for #4
    remote: str
    sessions: int
    cost_usd: float
    fix_command: str            # exact `halyard link-repo … --remote …`

def cost_by_client(sessions, *, range) -> list[ClientCostPoint]
def confidence_trend(sessions, *, range) -> list[ConfidencePoint]
def project_evidence(sessions, project_dir) -> list[ProjectEvidence]
def leakage(unattributed_log) -> list[LeakRow]
```

- Cost uses `cost_usd` as recorded (already correct per-model after
  v2.61; inherits v2.62 cache accuracy when that lands — no special
  casing here).
- Confidence band via `halyard.attribution.attribution_confidence`.
- Outcomes via existing `pr_state` on `AiSession` (same buckets as
  `outcome_report`).
- Human minutes per project via `build_human_time_report` (already
  per-project aware) — `None` when no timeclock (not 0).
- `leakage` reuses `doctor._group_unattributed_by_remote` + the v2.65
  remediation string builder (factor that string builder out of doctor
  into `moat`/shared so both use one source).

## Render layer (`dashboard.py`, inline SVG/HTML, no JS)

Reuse v2.64's chart primitive (the stacked-`<rect>` series + legend).
Four additive panels, draggable/collapsible per v2.42, placed
**above** the commodity stats panel:

1. **Cost-by-client** — stacked bars, x=week, y=USD, band/legend per
   client project; `$` axis, not tokens. Cost-trust styling carried
   through (e.g. allocated vs captured hatch as the dashboard already
   distinguishes).
2. **Attribution-confidence trend** — stacked bars per period; fixed
   color ramp timer→adrift (green→amber→grey); legend = current mix.
3. **Billable-evidence cards** — one card per client project: human
   time · AI cost · sessions · `▲shipped ◐in-flight ✗abandoned` ·
   confidence chip. The moat panel; visually primary.
4. **Leakage funnel** — descending by `$`; each row shows
   `remote — N sessions · $X` and the runnable fix; copy-safe text.

No charting dependency; static markup; offline.

## TUI

Headline parity only (information, not pixels): a compact
"Attribution & cost by project" text table (project · $ · sessions ·
confidence) — the cards/charts are dashboard-only.

## Moat-protection invariant (regression-guarded)

These panels render *before* the v2.64 commodity stats in the default
order. A test asserts the rendered dashboard places a moat panel
(cost-by-client or billable-evidence) ahead of the commodity stats
panel — encoding the "parity is additive, moat stays primary"
principle as an executable check, like v2.64's moat-protection test.

## Tests (`tests/test_v266_moat_visualization.py`)

1. `cost_by_client` buckets correctly by week × client; adrift bucket
   labelled, not dropped.
2. `confidence_trend` uses v2.65 bands; legacy `git`→`auto`.
3. `project_evidence` joins human time + cost + `pr_state` buckets +
   dominant confidence; `human_minutes` None when no timeclock.
4. `leakage` rows carry a runnable `link-repo` command; nothing
   written.
5. Renderers emit well-formed SVG/markup for a known fixture
   (structure, not pixels); empty data → graceful empty state.
6. Moat-protection: moat panel ordered before commodity stats.
7. Cost trust + outcome labels present (no unlabelled estimate).
8. Shared remediation-string builder used by both `doctor` and
   `moat.leakage` (one source of truth).

## Docs

`docs/PRD-local-activity-dashboard.md`: add the moat surface and state
it ranks above commodity parity. `current-direction.md`: one line that
the moat has a dedicated visual surface (v2.66) above the parity floor
(v2.64).

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap entry.
Feature changeset — full spec. Ranks above v2.64 in build order.
