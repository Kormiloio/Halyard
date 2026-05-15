# Proposal: v2.5 — CLI Decoupling

## The Problem
The `src/halyard/cli.py` module has grown to over 1,500 lines and contains significant business logic, interactive loops, and file manipulation. This mixing of CLI orchestration (Typer/Rich) with core logic makes the code harder to test, reuse, and maintain. For example, the `assign-unattributed` interactive loop and the `report` data aggregation are deeply embedded in Typer command functions.

## The Solution
Refactor Halyard to decouple CLI orchestration from core logic and interactive services.
- Move project scaffolding (`init`) to a dedicated service.
- Move interactive session recovery (`assign-unattributed`) to a dedicated service.
- Move reporting aggregation (`report`) further into the `reports.py` module.
- Move hub management logic out of `cli.py`.

The goal is to have `cli.py` focus exclusively on Typer command definitions, argument parsing, and UI rendering (Rich).

## Scope
- Create `src/halyard/orchestration.py` for interactive/multi-step CLI services.
- Refactor `src/halyard/reports.py` to include higher-level report orchestration.
- Update `src/halyard/cli.py` to delegate to these services.
- Maintain full behavioral compatibility and test coverage.
