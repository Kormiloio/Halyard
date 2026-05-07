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

## Identity Model

Org identity is file-based and local-first. An `org.toml` file at the Halyard
hub root defines org, teams, and user-to-team mappings. This can be machine-
generated from GitHub/SCIM or maintained manually. SSO integration is additive
and optional — the file is the source of truth regardless.

User identity is the git user email from the contributor's environment
(`git config user.email`). This is already recorded in session metadata.

## Sync Model

Sync is push-only from clients. Contributors decide when to sync. There is no
pull-based architecture in v3. A sync command (`halyard sync` or equivalent)
uploads normalized metadata records to a configured org endpoint.

## Cost Centers

Cost centers are mapped in `projects.toml` as an optional `cost_center` field
on each project. Finance teams that need finer control can supply an
`org-cost-centers.toml` file at the hub root that maps project slugs or team
slugs to cost center codes. The project-level field wins if both are present.

## Minimum Viable Governance Policy

Three built-in checks cover the governance floor:

1. **Collector health** — expected tools per user are configured; missing
   data triggers a health flag. "Expected" is inferred from history or
   configured explicitly.
2. **Unknown model** — any model slug not in the local pricing table is
   flagged for review.
3. **Unattributed rate** — when more than a configurable threshold (default
   10%) of a team's sessions are unattributed, the governance view raises
   a cleanup alert.
