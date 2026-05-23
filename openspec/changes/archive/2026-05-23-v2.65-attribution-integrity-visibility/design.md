# v2.65 — Attribution Integrity & Visibility: Design

## 1. Record the real chain rung (capture, additive)

Today collectors set `_attr_method = "timer"` or `"git"`. `"git"`
hides three very different rungs. Resolve and record the actual rung
when attribution is inferred (not via timer):

| Rung | Source | Confidence |
|---|---|---|
| `timer` | active `halyard start` | highest |
| `repo-map` | explicit `~/.halyard/repos.toml` remote→slug | high |
| `toml` | `halyard.toml` `[project].slug` walk-up | high |
| `git-auto` | derived `git/<repo-name>` slug | low |
| (none) | unattributed | none |
| `backfill` / `manual` | existing amendment provenance | as today |

The inference site (`infer_project` + the collector attribution
block) already *knows* which rung fired — it just discards it. Widen
`attr_method` to carry the specific rung (keep `timer`/`backfill`/
`manual`; replace the catch-all `git` with `repo-map`/`toml`/
`git-auto`). `attr_method` is already a serialized `AiSession` field,
so this is a value-set widening, **not** a new field. Parser/back-
compat: an old `attr_method=git` token maps to confidence `git-auto`
(the safe lower bound — never inflate an old guess to "mapped").

## 2. Attribution confidence (derive + surface)

`src/halyard/attribution.py` (new, small, tested):

```python
AttributionConfidence = Literal["timer","mapped","toml","auto","none","unknown"]

def attribution_confidence(session) -> AttributionConfidence:
    if not session.project:                 return "none"
    return {
        "timer": "timer", "repo-map": "mapped", "toml": "toml",
        "git-auto": "auto", "git": "auto",      # legacy → safe lower bound
        "backfill": "unknown", "manual": "unknown",
    }.get(session.attr_method or "", "unknown")

def attribution_mix(sessions) -> dict[AttributionConfidence, int]
```

Surface, mirroring the existing cost-trust mix:

- **CLI** (`halyard report`): an "Attribution" line —
  `timer N · mapped N · toml N · auto N · adrift N`.
- **Dashboard**: a confidence chip on the attribution panel; adrift
  and `auto` visually distinct from `timer`/`mapped` (the defensible
  ones). Additive panel content; v2.42 layout respected; moat panel
  stays primary.
- **MCP**: `work_summary` gains an `attribution_mix` block (metadata
  only — already the contract).

## 3. Attribution-quality canary (`doctor`, v2.59 pattern)

`doctor._attribution_quality_checks(project_dir, hub_dir)`:

- **Adrift-rate regression:** compare adrift share of the most recent
  `_ATTR_WINDOW` (=20) sessions vs the prior window; `warning` if it
  rose past a margin (e.g. +20pp) — tunable constant.
- **Per-remote regression:** a remote that had attributed sessions in
  the prior window but only `unattributed` ones in the recent window
  → `warning` (the moved-project / `repos.toml`-drift signal). Reuses
  `_group_unattributed_by_remote`.
- `warning`, never `error` (exit-code contract preserved, like v2.52/
  v2.59); flows through `DoctorReport` → dashboard/TUI inherit it.

## 4. One-command remediation

The existing `state.unattributed` doctor check says "run halyard adopt
in each repo". Upgrade its `fix` to emit, per grouped remote, the
exact line: `halyard link-repo <suggested-slug> --remote <remote>`
(or `halyard adopt <path>` when a local path is known). Proposes
only — no write. Suggested slug derived from the repo name, never
applied automatically.

## Tests (`tests/test_v265_attribution_integrity.py`)

1. Each rung → correct `attribution_confidence`; legacy `git` →
   `auto` (never `mapped`); no project → `none`.
2. Collector records `repo-map` vs `toml` vs `git-auto` distinctly
   (fixtures: repos.toml present / halyard.toml walk-up / bare git).
3. `attribution_mix` aggregates correctly over a mixed set.
4. Back-compat: an old `attr_method=git` line parses, confidence
   `auto`, display unchanged otherwise.
5. Canary: adrift-rate regression fires `warning`; stable adrift does
   not; per-remote regression fires; brand-new remote does not.
6. Exit-code contract: only `attr.*` warnings ⇒ `has_errors` False.
7. Remediation `fix` string contains a runnable `link-repo`/`adopt`
   command per remote; no file is written by doctor.
8. MCP `work_summary` includes `attribution_mix`.

## Docs

`docs/PRD-halyard.md` "Trust label" concept extended to note
attribution confidence is now a first-class, surfaced label (parity
with cost trust). `current-direction.md` Governing Principles already
states moat protection; add one line that attribution carries an
explicit confidence label like cost.

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap entry.
Phased: §1+§2 (capture+surface) can ship before §3+§4 if desired.
