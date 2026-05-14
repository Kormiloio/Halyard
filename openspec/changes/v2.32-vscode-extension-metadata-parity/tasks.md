# Tasks: v2.32 - VS Code Extension and Metadata Parity

## Planning

- [x] Write PRD for VS Code extension and metadata parity.
- [x] Write ARD for VS Code extension and metadata parity.
- [x] Write OpenSpec proposal.
- [x] Write OpenSpec design.
- [x] Write OpenSpec requirements.
- [ ] Review and approve field vocabulary before implementation.
- [x] Decide whether VS Code extension lives in this repo or a separate repo.

## Schema

- [x] Add optional interaction metadata fields to `AiSession`.
- [x] Serialize and parse new fields with backward compatibility.
- [ ] Validate enum and numeric metadata fields.
- [ ] Add tests for missing vs zero interaction data.
- [ ] Add tests preventing unsafe content serialization.

## CLI

- [x] Extend `record-session` with metadata flags or a JSON payload mode.
- [x] Add `source=vscode-extension` support.
- [ ] Add clear error messages for invalid metadata payloads.
- [x] Preserve current manual VS Code task behavior.

## Collector Parity

- [ ] Add collector coverage table documentation.
- [x] Update Claude Code collector to populate safe interaction counts where available.
- [x] Update Cursor collector to populate safe interaction counts where available.
- [x] Update Gemini CLI collector to normalize existing telemetry into shared fields.
- [x] Update Codex Desktop importer to populate safe interaction counts where available.
- [x] Keep unavailable fields omitted or explicitly marked unavailable.

## VS Code Extension

- [x] Scaffold VS Code extension.
- [x] Add configuration for Halyard executable path.
- [x] Add status bar item.
- [x] Add start, stop, record, open dashboard, and show scope commands.
- [x] Capture safe extension-observed metadata.
- [x] Invoke Halyard CLI for writes.
- [x] Add recovery prompt for unfinished work blocks.
- [x] Add extension tests for command construction and privacy boundaries.

## Reports and UI

- [x] Show interaction counts where available.
- [x] Show unavailable metadata distinctly from zero.
- [x] Add work-shape summaries without productivity scoring.
- [x] Update dashboard/TUI labels and help text.

## Documentation

- [x] Update README technical section with metadata parity coverage.
- [ ] Update troubleshooting docs for VS Code extension setup.
- [x] Add privacy note explaining metadata-only VS Code capture.
