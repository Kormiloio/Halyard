# Governance Spec

## Requirement: collector health

The org dashboard MUST show capture health across users and teams.

### Scenario: missing collector

- WHEN a user's expected collector has not reported data
- THEN the governance view flags the user or device as missing capture

### Scenario: unknown model

- WHEN a session uses an unknown model
- THEN the governance view shows the model as needing pricing or policy review

## Requirement: privacy boundary

The org dashboard MUST not expose sensitive work content by default.

### Scenario: default sync

- WHEN local Halyard data syncs to the org dashboard
- THEN prompts, code contents, transcripts, and file contents are excluded

### Scenario: metadata reporting

- WHEN a manager views usage
- THEN they see metadata, costs, attribution, and health
- AND they do not see prompt or code content

## Requirement: audit posture

The org dashboard MUST preserve enough metadata for audit and cost review.

### Scenario: audit export

- WHEN an admin exports audit data
- THEN records include timestamps, user, team, project, tool, model, source,
  cost, and trust labels
