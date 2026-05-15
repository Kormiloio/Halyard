# Design: v2.5 — CLI Decoupling

## Architectural Changes

### 1. New Module: `src/halyard/orchestration.py`
This module will handle interactive workflows and multi-step CLI operations that involve user prompts (using `typer.prompt` or `typer.confirm`).
- `scaffold_project(target_dir, business_name, hub=False)`: Encapsulates the logic from `halyard init`.
- `interactive_assign_unattributed(project_dir=None, explicit_project=None)`: Encapsulates the session recovery loop.

### 2. Refactored Module: `src/halyard/reports.py`
High-level report aggregation logic will be extracted from `cli.py` to make it reusable and testable.
- `build_filtered_ai_report(...)`: Handles period resolution and slug/client filtering.
- `get_pricing_staleness(...)`: Moved from CLI.

### 3. Refactored Module: `src/halyard/hub.py`
Hub state reporting will be centralized.
- `get_hub_status() -> HubStatus`: Returns a summary of the current hub (path, session count).

### 4. Thin CLI: `src/halyard/cli.py`
Typer commands will become delegators.
Example:
```python
@app.command()
def init(hub: bool = False):
    from halyard.orchestration import scaffold_project
    scaffold_project(Path.cwd(), _detect_business_name(), hub=hub)
```

## Data Flow
`CLI (typer)` -> `Orchestration / Service (logic)` -> `Data Model / Log (file IO)`
