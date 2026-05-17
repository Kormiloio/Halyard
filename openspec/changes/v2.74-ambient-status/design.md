# v2.74 — Ambient Status: Design

> Spec only. Decisions are recorded in
> [ARD-ambient-status.md](../../../docs/ARD-ambient-status.md); this
> is the implementation shape, to be verified against current code
> before any build.

## Status contract (the one object)

Extend the existing `status` command (cli_session.py) to add
`--json` output of a `StatusSnapshot`:

```
StatusSnapshot:
  generated_at: datetime
  capture:                       # from doctor builders
    healthy: bool
    hooks: {claude,cursor,gemini,...: "ok"|"missing"|"warn"}
    minutes_since_last_capture: int | None
  spend:                         # from build_ai_report / sum_spend
    today_usd: float
    month_usd: float
    by_client: [{slug, month_usd}]   # top N
  adrift: {count: int, usd: float}   # existing leakage/unattributed path
  budgets:                       # budgets.toml + month-to-date
    - slug: str
      month_limit_usd: float | None
      month_spend_usd: float
      pct: int
      projected_month_end_usd: float        # mtd / day_of_month * days_in_month
      days_until_limit: int | None          # (limit - mtd) / daily_run_rate
      estimate: true                        # ALWAYS true — never "measured"
```

Built **only** from existing functions — audit + cite each source in
tasks.md before coding. If any field needs new capture, it is cut,
not added (mission guardrail).

Emitted through the v2.69 `jsonio.emit` seam (datetime→ISO, etc.) so
it shares the established JSON contract and error shape.

## Projection (the CodexBar-reframe, on-mission)

Deliberately the simplest defensible math, labeled an estimate:

- `daily_run_rate = month_spend_usd / max(1, day_of_month)`
- `projected_month_end_usd = daily_run_rate * days_in_month`
- `days_until_limit = floor((month_limit - month_spend) / daily_run_rate)`
  when a limit exists and run-rate > 0; else `None`.

No smoothing, no ML, no false precision. `estimate: true` is
non-removable; renderers must visually mark it (e.g. `~`).

## Renderers

### `halyard status --watch` (all platforms — the floor)

Clear-and-redraw the snapshot every `interval` (default 30 s,
`--interval`). One screen: a health line, spend line, top budgets
with burn (`acme:web ▓▓▓▒░ 78% · ~$310 proj / $400 · ~6d to limit`),
adrift line. Pure stdlib; Ctrl-C exits. No new dependency.

### macOS menu-bar shim (optional, spike-gated)

- Optional extra `halyard[menubar]` (PyObjC/`rumps`).
- A `halyard menubar` entry point the existing `halyard service`
  launchd plist can target instead of (or alongside) the dashboard.
- Title = compact health/spend; dropdown = the snapshot + "Open
  dashboard" / "Open project". Polls the in-process builders on the
  same interval — **does not require the HTTP dashboard running** and
  **binds no socket**.
- If Phase-0 spike fails: this section is deferred; `--watch` ships.

## Performance

Per tick: trailing-window read via the SQLite read-model cache the
builders already use — NOT a full `parse_sessions` re-aggregate.
Reuse, measure in the spike against a 50k-line log; a tracing-aware
perf test (the v2.71 `perf_ceiling` fixture) guards it.

## Security / privacy (test-enforced)

- Reader only: no file is written by `--watch` or the shim.
- A test asserts the snapshot code path never imports/opens any
  provider credential location (no `~/.gemini` creds, no keychain,
  no cookies) — only Halyard's own files.
- `estimate: true` present on every budget projection (test-pinned).
- No network bind in the menu-bar shim (test/spike-verified).

## Tests (`tests/test_v274_ambient_status.py`)

1. `status --json` emits the documented `StatusSnapshot` keys; values
   equal what `report`/`budget`/`doctor` already return (single
   -source parity — the core test).
2. Projection math: known mtd/day → expected
   `projected_month_end_usd` / `days_until_limit`; `estimate` always
   true; run-rate 0 → `days_until_limit is None` (no divide-by-zero).
3. No-budget / no-sessions / empty project → clean snapshot, no
   exception.
4. Privacy: snapshot build touches only Halyard files (assert via a
   patched open/`Path` allowlist or import audit).
5. `--watch` renders one frame from a fixture without looping
   forever (inject `max_frames=1`); tracing-aware perf bound on the
   per-tick build over a large log.
6. Menu-bar (only if spike passes): entry point importable, renders
   title text from a snapshot fixture, binds no socket.

## Decision gate

If the status contract cannot be built **without new captured data**,
the feature is reduced to what existing data supports or shelved —
not extended with new capture. Recorded, not worked around.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap
entry. Feature changeset; menu-bar piece Phase-0-gated.
