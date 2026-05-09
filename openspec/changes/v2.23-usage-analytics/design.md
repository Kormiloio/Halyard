# Design: v2.23 - Usage Analytics

## Architecture

Usage Analytics should be built as a shared service first, then rendered by the
CLI and dashboard.

The service reads parsed `AiSession` objects and returns display-neutral view
models. The dashboard should not perform its own aggregation logic, and the CLI
should not duplicate chart calculations.

Recommended module:

```text
src/halyard/usage.py
```

Recommended dashboard integration:

```text
src/halyard/dashboard.py       # route/render hook for Usage view
src/halyard/cli.py             # `halyard usage` and `--json`
```

## View models

```python
@dataclass(frozen=True)
class UsageRange:
    key: Literal["all", "30d", "7d"]
    label: str
    start: date | None
    end: date

@dataclass(frozen=True)
class UsageSummary:
    sessions: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_write_tokens: int
    token_data_missing_sessions: int
    total_cost_usd: float
    cost_missing_sessions: int
    active_days: int
    current_streak_days: int
    longest_streak_days: int
    peak_hour: int | None
    favorite_model: str | None
    unattributed_sessions: int

@dataclass(frozen=True)
class DailyUsageBucket:
    day: date
    sessions: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    has_missing_token_data: bool
    by_model: list[ModelUsageBucket]

@dataclass(frozen=True)
class ModelUsageBucket:
    model: str
    sessions: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float
    token_share: float
    cost_share: float
    session_share: float

@dataclass(frozen=True)
class ToolUsageBucket:
    tool: str
    sessions: int
    tokens: int
    cost_usd: float
    session_share: float
```

The exact class names may change during implementation, but the separation of
summary, daily buckets, model buckets, and tool buckets should remain.

## Range semantics

Ranges are based on local dates.

- `all`: includes every parsed session.
- `30d`: includes sessions whose local start date is within the last 30 days,
  including the end date.
- `7d`: includes sessions whose local start date is within the last 7 days,
  including the end date.

The end date defaults to today. Tests should be able to pass a fixed `now`.

## Metrics

### Sessions

Count parsed session records after amendments have been applied by the parser.

### Tokens

Total tokens are:

```text
input + output + cache_read + cache_write
```

The UI should also display input and output separately in detailed views.

If `tokens_available` is false, the session counts toward sessions and active
days but should increment missing-token metadata. Missing token data must not
be displayed as zero usage.

### Cost

MVP uses captured `cost_usd` from sessions. Allocated seat/credit cost can be
added later by reusing the ledger service.

Rows with zero captured cost should remain visible. A zero cost is not
necessarily missing cost; missing cost should be represented only when the
parser or future schema can distinguish it.

### Active days

Count distinct local dates with at least one session in the selected range.

### Streaks

Current streak is the number of consecutive local days ending on the range end
date that have at least one session.

Longest streak is the longest consecutive run of active days within the
selected range.

### Peak hour

Peak hour is the local hour with the most session starts. Ties should choose
the earliest hour for deterministic output.

### Favorite model

Favorite model defaults to the model with the most total tokens. If no token
data is available, fall back to session count. Ties should choose the model
with the larger session count, then lexical order.

## Dashboard UX

The dashboard should add a Usage view or section with two tabs:

- Overview
- Models

The Overview tab should show:

- range segmented control: All, 30d, 7d;
- metric cards;
- activity heatmap;
- tool share;
- subtle warnings for unattributed or missing-token sessions.

The Models tab should show:

- stacked daily model chart;
- model breakdown rows;
- metric toggle for tokens, cost, and sessions when feasible.

The first version can use server-rendered HTML and CSS. No frontend build
pipeline is required.

## CLI UX

Add:

```bash
halyard usage
halyard usage --range 30d
halyard usage --json
```

Text output should summarize the same metrics without trying to reproduce the
full visual charts. JSON output should expose the shared view model for tests,
automation, and future UI work.

## Styling

Usage Analytics can be more visual than the Glass Cockpit, but should still
look like a work tool.

Implementation guidance:

- compact stat cards;
- stable chart and heatmap dimensions;
- no marketing hero;
- no prompt/code content;
- distinct model colors;
- semantic warning states;
- accessible labels for charts.

## Testing

Unit tests should cover:

- range filtering;
- day bucket generation;
- active days;
- current and longest streak;
- peak hour tie-breaking;
- favorite model selection;
- model share percentages;
- handling `tokens_available=false`;
- empty log behavior;
- JSON shape for `halyard usage --json`.

Dashboard rendering tests should check that the usage view includes the core
sections and does not render private content fields.

