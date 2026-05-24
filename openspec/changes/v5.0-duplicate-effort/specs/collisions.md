# Behavior Spec: Duplicate-Effort Detection (v5.0)

## R1: Concurrent Collision Detection
The Hub MUST identify when two tools are working on the same branch simultaneously.

**Scenario: Concurrent tool usage**
- GIVEN a timer is active for project `halyard` on branch `feat/hub`
- WHEN a second tool emits a session with the same branch name
- THEN the Hub MUST record a "Collision" event
- AND the Bridge dashboard MUST display a "Concurrent Collision" warning.

## R2: CLI Warning
The CLI MUST warn the user if they start a timer on a branch that recently had AI activity.

**Scenario: Sequential collision warning**
- GIVEN a session was logged on branch `fix/bug` 5 minutes ago
- WHEN the user runs `halyard start` on the same branch
- THEN the CLI MUST display: `[yellow]Note: Branch 'fix/bug' has recent AI activity (5m ago). Overlap detected.[/]`

## R3: Historical Analysis
The Analytical layer MUST calculate "Overlapping Effort".

**Scenario: Reporting overlap**
- GIVEN three sessions occurred on the same branch with overlapping timestamps
- WHEN the user views the "Efficiency" report
- THEN Halyard MUST show the "Overlapping Effort" as the sum of the redundant durations.
