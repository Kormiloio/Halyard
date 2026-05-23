# Spec: Attribution Integrity & Visibility

## Requirement: Record the real attribution rung

When attribution is not via the active timer, the collector MUST
record the specific chain rung in `attr_method`: `repo-map` (explicit
`repos.toml` mapping), `toml` (`halyard.toml` walk-up), or `git-auto`
(derived `git/<repo>` slug). `timer`, `backfill`, `manual` are
unchanged. This is a value-set widening of the existing field — no
new schema, no format change.

### Scenario: explicit repo mapping
- GIVEN `repos.toml` maps the repo's remote to `acme:web`
- THEN the session's `attr_method` is `repo-map`.

### Scenario: bare git repo
- GIVEN no timer, no `halyard.toml`, no `repos.toml` entry
- THEN `attr_method` is `git-auto`.

## Requirement: Attribution confidence is derived and never inflated

`attribution_confidence(session)` MUST map rung → confidence
(`timer` > `mapped` > `toml` > `auto` > `none`/`unknown`). A legacy
`attr_method=git` MUST resolve to `auto` (the safe lower bound),
never `mapped`. No project ⇒ `none`.

## Requirement: Confidence surfaced like cost trust

The attribution mix MUST appear in `halyard report` (CLI), the
dashboard attribution panel, and the MCP `work_summary`, the way the
cost trust mix already is. Adrift and `auto` MUST be visually distinct
from `timer`/`mapped`.

## Requirement: Attribution-quality canary

`halyard doctor` MUST emit a `warning` (never `error`) when the adrift
share of the recent window regresses past the margin vs the prior
window, OR when a remote that had attributed sessions in the prior
window has only unattributed sessions in the recent window.

### Scenario: adrift regression
- GIVEN recent sessions are markedly more unattributed than the prior
  window
- THEN a `attr.*` `warning` check is present; `has_errors` stays
  False.

### Scenario: stable attribution
- GIVEN adrift share is steady
- THEN no `attr.*` check.

## Requirement: Remediation proposes, never writes

The unattributed doctor check's `fix` MUST contain a runnable
`halyard link-repo … --remote …` (or `halyard adopt …`) per grouped
remote. `halyard doctor` MUST NOT modify `repos.toml`, any
`halyard.toml`, or the log.

## Requirement: Back-compat & no cost-path change

Existing `ai-sessions.log` lines MUST parse and display unchanged
(legacy `git` → `auto` confidence). Nothing in cost computation or
the v2.61 model-breakdown path may change.
