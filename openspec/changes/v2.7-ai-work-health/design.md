# Design: v2.7 — AI Work Health

## Module layout

```
src/halyard/
└── work_health.py      # signal detectors + report model
```

The CLI command lives in `cli.py`. All detection logic lives in
`work_health.py` as pure functions over `list[AiSession]`. No new files are
written. No network access.

## Data model

```python
@dataclass(frozen=True)
class HealthSignal:
    category: str           # signal category name
    sessions: list[AiSession]  # flagged sessions
    detail: str             # one-line context per flagged session
    available: bool         # False when data for this signal is absent

@dataclass(frozen=True)
class WorkHealthReport:
    period: str
    session_count: int
    signals: list[HealthSignal]
```

`HealthSignal.available = False` when no sessions in the period have the
fields required for that signal (e.g. no `tool_calls` populated). This is
distinct from `available = True, sessions = []` (data present, no flags fired).

## Signal detectors

Each detector is a pure function:

```python
def detect_high_error_rate(sessions: list[AiSession]) -> HealthSignal: ...
def detect_wall_vs_active(sessions: list[AiSession]) -> HealthSignal: ...
def detect_high_spend_low_delta(sessions: list[AiSession]) -> HealthSignal: ...
def detect_repeated_attempts(sessions: list[AiSession]) -> HealthSignal: ...
def detect_unattributed_high_cost(sessions: list[AiSession]) -> HealthSignal: ...
```

### High error rate

```python
THRESHOLD_MIN_CALLS = 5
THRESHOLD_ERROR_RATE = 0.25

flagged = [
    s for s in sessions
    if s.tool_calls is not None
    and s.tool_calls >= THRESHOLD_MIN_CALLS
    and (s.tool_errors or 0) / s.tool_calls > THRESHOLD_ERROR_RATE
]
available = any(s.tool_calls is not None for s in sessions)
```

### Wall time vs active time

```python
THRESHOLD_ACTIVE_RATIO = 0.3  # active < 30% of wall = flagged

flagged = [
    s for s in sessions
    if s.wall_seconds is not None
    and s.agent_active_seconds is not None
    and s.wall_seconds > 0
    and s.agent_active_seconds / s.wall_seconds < THRESHOLD_ACTIVE_RATIO
]
available = any(
    s.wall_seconds is not None and s.agent_active_seconds is not None
    for s in sessions
)
```

### High spend, low code delta

```python
THRESHOLD_COST_USD = 0.50
THRESHOLD_LINES_PER_DOLLAR = 5.0  # fewer than 5 lines per dollar flagged

flagged = [
    s for s in sessions
    if s.code_added is not None
    and s.cost_usd >= THRESHOLD_COST_USD
    and (s.code_added + (s.code_removed or 0)) / s.cost_usd < THRESHOLD_LINES_PER_DOLLAR
]
available = any(s.code_added is not None for s in sessions)
```

### Repeated attempts

```python
from collections import Counter

THRESHOLD_REPEATS = 3

def _day_key(s: AiSession) -> tuple[str, str, str]:
    branch = next((t.removeprefix("branch:") for t in s.tags if t.startswith("branch:")), "")
    return (s.project or "", branch, s.start.strftime("%Y-%m-%d"))

counts = Counter(_day_key(s) for s in sessions)
flagged_keys = {k for k, n in counts.items() if n >= THRESHOLD_REPEATS and k[0]}
flagged = [s for s in sessions if _day_key(s) in flagged_keys]
available = True  # always computable
```

### Unattributed high-cost sessions

```python
unattributed = [s for s in sessions if not s.project and s.cost_usd > 0]
if not unattributed:
    available = bool(sessions)
    flagged = []
else:
    costs = sorted(s.cost_usd for s in sessions if s.cost_usd > 0)
    if costs:
        p75 = costs[int(len(costs) * 0.75)]
        flagged = [s for s in unattributed if s.cost_usd >= p75]
    else:
        flagged = unattributed
    available = True
```

## CLI command

```
halyard health [--period today|week|month|all] [--project SLUG] [--format text|json]
```

Resolves `project_dir` via `find_project_dir() or find_hub()`. Parses
sessions. Applies all five detectors. Renders report.

## Text output format

```
AI Work Health — month
─────────────────────────────────────────────────────

These are operational signals, not productivity scores.

● High tool error rate                     2 sessions flagged
  2026-05-07 10:30  gemini-cli  acme:auth  45c 12e (27%)  $0.32
  2026-05-07 15:00  gemini-cli  acme:auth  20c  6e (30%)  $0.18

● Wall time ≫ active time                  No data — requires agent_active_seconds
● High spend, low code delta               No data — requires code_added
● Repeated sessions — same project/branch  0 sessions flagged
● Unattributed high-cost sessions          1 session flagged
  2026-05-05 09:00  claude-code  (none)  $1.20

─────────────────────────────────────────────────────
12 sessions analysed.
```

## JSON output shape

```json
{
  "period": "month",
  "session_count": 12,
  "signals": [
    {
      "category": "high_error_rate",
      "label": "High tool error rate",
      "available": true,
      "flagged_count": 2,
      "sessions": [
        { "start": "...", "tool": "gemini-cli", "project": "acme:auth",
          "tool_calls": 45, "tool_errors": 12, "cost_usd": 0.32 }
      ]
    }
  ]
}
```

## Thresholds are not configuration (v2.7)

The thresholds are constants in `work_health.py`. They are not user-configurable
in v2.7. If user-adjustable thresholds prove necessary they will be added in a
later change with a spec update.

## Testing

Each detector is tested independently with crafted session lists. No I/O
required. The CLI command is tested with a monkeypatched `parse_sessions`.
