# Design: v2.25 Honors and Achievements

## Approach

The honors system is a **pure read layer** over existing data. It imports from
`halyard.ai_log` and `halyard.reports` but writes nothing. This means it cannot
break any existing behavior and needs no migration, no new file format, and no
backward-compatibility shims.

## Module structure

All computation lives in `src/halyard/achievements.py`. The CLI command and
dashboard panel import from it but do not contain business logic.

```
achievements.py
  RankDef          frozen dataclass — rank definition
  Medal            frozen dataclass — medal definition
  ServiceRecord    frozen dataclass — computed state for one user
  RANKS            list[RankDef]   — catalog, ordered by level
  MEDALS           list[Medal]     — catalog, ordered by unlock order
  build_service_record(project_dir, sessions, *, as_of=None) -> ServiceRecord
  _extract_watches(project_dir) -> list[_Watch]
  _watch_streak(watches, *, as_of) -> int
  _clean_watch_streak(clean_days, *, as_of) -> int
  _clean_watch_days(watches, sessions) -> set[date]
  _evaluate_rank(attributed_count) -> (RankDef, RankDef|None, int)
  _evaluate_medals(project_dir, sessions, watches, clean_days) -> list[Medal]
  _compute_proof_score(sessions) -> int
```

## Key design decisions

### Rank threshold: attributed sessions only

Unattributed sessions do not count toward rank. This directly enforces the
"reward clean proof, not raw hours" philosophy. A user cannot game rank by
dumping hundreds of unattributed sessions.

### Watch = timeclock i/o pair

A "watch" is one completed `halyard start → halyard stop` cycle, which produces
one `i … o` pair in `time.timeclock`. The implementation calls `parse_timeclock`
from `halyard.reports` — same parser used everywhere else, no duplication.

### Streak computed as_of a date parameter

`_watch_streak` and `_clean_watch_streak` both accept `as_of: date | None` so
tests can pin the reference date without mocking `datetime.now`. Production
callers pass `None` (defaults to today).

### Medal evaluation is stateless per call

`_evaluate_medals` reads the sessions list, watches list, and clean_days set
that are passed in. It does not re-read files. This keeps it pure and testable
without touching disk.

### Harbor Master uses directory scan

The `invoices/` directory is already the canonical invoice storage location.
Checking `any(invoice_dir.iterdir())` is the simplest correct signal without
inventing a new "invoice exported" event.

### Rescue at Sea approximation

The exact semantics ("was adrift, now not") would require history or a
completion event. The v1 approximation (adrift_now == 0 AND backfilled >= 5)
is a good proxy: if a user had a significant backlog and cleared it, they likely
rescued sessions. This is documented in proposal.md as a known approximation.

### No new data stored

`ServiceRecord` is computed on demand and never persisted. The dashboard
re-computes it on each page render (same pattern as all other panels). The CLI
computes it once per invocation. This avoids any caching complexity.

## CLI rendering

`halyard honors` uses Rich `Panel` and `Text` directly, following the same
pattern as `halyard stop` (stop card). No new Rich helper functions — the
rendering is inline in the command.

## Dashboard panel placement

Captain's Quarters is placed immediately after the Current Voyage panel (second
panel in the grid). This gives it prominence without displacing the live session
stream. It is full-width (`span-12`) like the heatmap and sessions-adrift panels.

## CSS approach

New classes follow the existing `cq-*` prefix pattern (consistent with
`voyage-*` for the Current Voyage panel). All styles are appended to the
existing `_CSS` string — no separate stylesheet, no framework.

## Trade-offs considered

| Option | Decision | Reason |
|--------|----------|--------|
| Persist ServiceRecord to cache.db | Rejected | Pure read layer is simpler; compute time is negligible |
| Separate `honors.py` vs inline in `achievements.py` | All in achievements.py | Only one module needed; CLI/dashboard each do their own rendering |
| Click-for-description JS modal | Used title= attribute instead | Zero JS for hover, works in all browsers, no modal state to manage |
| Rank based on total vs attributed sessions | Attributed only | Enforces the core philosophy |
