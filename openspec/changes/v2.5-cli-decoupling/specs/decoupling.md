# Spec: CLI Decoupling

## Scenario: Project Initialization
**Given** the user runs `halyard init`
**When** the CLI command is invoked
**Then** it should delegate to `orchestration.scaffold_project`
**And** the same file structure should be created as before
**And** the console output should remain identical.

## Scenario: Interactive Session Recovery
**Given** the user has unattributed sessions
**And** the user runs `halyard assign-unattributed`
**When** the CLI command is invoked
**Then** it should delegate to `orchestration.interactive_assign_unattributed`
**And** the user should be prompted for each session as before
**And** the choices (assign/hub/discard/skip) should work identically.

## Scenario: Reporting
**Given** the user runs `halyard report`
**When** the CLI command is invoked
**Then** it should use the updated `reports.py` to filter and aggregate data
**And** the Rich-based terminal tables should look exactly the same.
