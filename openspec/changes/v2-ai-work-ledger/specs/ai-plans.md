# AI Plans Spec

## Requirement: plan configuration

Halyard MUST support local configuration for AI subscriptions, seats, credits,
and API billing assumptions.

### Scenario: seat plan

- WHEN the user configures a monthly Claude Max plan
- THEN Halyard stores the monthly price, tool slug, billing type, start date,
  and allocation rule in `ai-plans.toml`

### Scenario: credit plan

- WHEN the user configures a Cursor or Factory credit plan
- THEN Halyard stores the included credits and monthly price
- AND reports can convert credits to USD when enough information exists

### Scenario: direct API billing

- WHEN the user configures a direct API tool
- THEN Halyard uses `cost_usd` from `ai-sessions.log`
- AND does not allocate an additional monthly seat cost unless configured

## Requirement: allocation rules

Halyard MUST support multiple allocation rules for non-API costs.

### Scenario: active-minute allocation

- WHEN a seat plan uses `allocation = "active_minutes"`
- THEN Halyard allocates the monthly plan cost across sessions by session
  duration within the billing period

### Scenario: session-count allocation

- WHEN a seat plan uses `allocation = "session_count"`
- THEN Halyard allocates the monthly plan cost evenly across matching sessions
  within the billing period

### Scenario: manual allocation

- WHEN a plan uses `allocation = "manual"`
- THEN Halyard shows usage without assigning USD cost automatically
- AND reports explain that the plan cost is unallocated

## Requirement: local-first storage

Plan configuration MUST be plain text and editable by humans.

### Scenario: initialized project

- WHEN the user runs `halyard init`
- THEN Halyard creates a commented `ai-plans.toml` template
- AND the file contains no real vendor credentials or secrets
