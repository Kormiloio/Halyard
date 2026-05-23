# Proposal: v3.7 — GitHub Copilot Importer

## Why this exists

GitHub Copilot is the most widely used AI developer tool, but in Halyard
it is currently limited to manual task capture (`tool=vscode`). While
Copilot does not offer a public hook surface like Claude Code or Cursor,
a research spike (2026-05-23) discovered that the VS Code extension
persists detailed session metadata to internal workspace storage.

v3.7 introduces a native **GitHub Copilot Importer** that retroactively
collects these records, bringing automated token counts, interaction
metrics, and outcome data (files touched) to Copilot users for the first
time.

## What changes

- **New Collector:** `src/halyard/collectors/copilot.py` — a retroactive
  importer similar to the Codex collector.
- **Automated Discovery:** Scans VS Code's `workspaceStorage` directory
  to find and associate Copilot sessions with Halyard projects.
- **Metadata Capture:**
  - **Timing:** Exact start/end times derived from JSONL timestamps.
  - **Tokens:** Extracts `completionTokens` (output) per turn.
  - **Interactions:** Counts user/assistant messages and tool calls.
  - **Outcomes:** Records the number of unique files modified during
    the session from the editing state manifest.
- **Privacy Enforcement:** Strictly parses metadata only. Every prompt,
  response text, and code snippet is discarded during the parse.
- **Roadmap:** Item 61 in `openspec/project.md`.

## User Stories

- **As a Copilot user**, I want my background chat and editing activity
  to appear in Halyard automatically so I don't have to manually log it.
- **As a developer**, I want to see how my Copilot usage (tokens/cost)
  compares to my Claude Code and Cursor usage across different projects.

## Success Criteria

- `halyard import-copilot`Retroactively finds and logs Copilot sessions.
- `halyard outcome sync` includes Copilot data in the daily rollup.
- All sessions are correctly attributed to the project folder where the
  work occurred.
- Zero PII or code content leaked into `ai-sessions.log`.

## Out of Scope

- Copilot CLI capture (no local history found during spike).
- Real-time "hook" capture (requires monitoring internal VS Code files).

## Risks and Trade-offs

- **Storage Layout:** VS Code's internal storage is undocumented and
  may change between versions.
- **Token Accuracy:** Copilot currently only reports completion (output)
  tokens in the local logs; input tokens are not yet discoverable and
  will be marked as unavailable.
- **Disk I/O:** Scanning hundreds of workspace storage folders can be
  slow; the importer will use mtime-based filtering to only scan
  recent folders.
