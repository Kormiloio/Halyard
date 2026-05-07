# Design

## Architecture

The org admin dashboard is a reporting projection over synchronized local
Halyard ledgers. Each contributor's `ai-sessions.log` remains the local source
of truth. Sync converts those records into normalized org events.

## Data Flow

1. Local collectors write `ai-sessions.log`.
2. A sync process uploads normalized metadata records.
3. The org service indexes records by org, team, project, user, tool, model,
   source, and billing period.
4. Dashboards query the reporting projection.

## Privacy Boundary

Default sync includes metadata only:

- timestamps;
- tool/model;
- token counts;
- costs;
- attribution fields;
- source and trust labels.

Prompts, code, transcripts, and file contents are excluded by default.

## Rollup Dimensions

- organization;
- department;
- team;
- project;
- user;
- tool;
- model;
- source;
- billing model;
- cost center;
- time period.

## Trust Labels

Every aggregate must preserve underlying cost quality:

- captured;
- calculated;
- allocated;
- inferred;
- missing.

Aggregates should show mixed-trust values instead of flattening everything into
one false-precision total.

## Scale Target

Initial design target: 500 users, 1 year of AI session logs, sub-second
dashboard queries for common monthly/team/project rollups.

## Open Questions

- What is the org identity model: Halyard-native users, SSO, or GitHub/SCIM
  mapping?
- Should sync be push-only from clients or pull-based from managed agents?
- How are cost centers mapped: project config, identity provider metadata, or
  finance upload?
- What is the minimum viable governance policy model?
