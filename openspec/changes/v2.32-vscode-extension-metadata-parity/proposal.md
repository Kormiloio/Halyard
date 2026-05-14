# Proposal: v2.32 - VS Code Extension and Metadata Parity

## Problem

Halyard captures AI work across multiple tools, but metadata depth is uneven.
Gemini CLI has rich operational telemetry. Claude Code, Cursor, and Codex
Desktop capture strong baseline usage and git metadata, but weaker interaction
shape. VS Code/Copilot capture is currently manual through a task, which is
honest but clunky.

Users need to understand not only what AI cost, but how much human interaction
was needed to produce the work. That requires shared metadata fields across
tools: interaction counts, suggestion counts, tool calls, errors, timing,
code delta, file-count-only outcome shape, and test/build status where
available.

## Decision

Define a metadata parity layer before implementation:

- Add a VS Code extension plan that shells out to the local Halyard CLI.
- Extend the session schema with optional metadata-only interaction fields.
- Require every collector to map native signals into the same field vocabulary
  when available.
- Keep unavailable values explicit.
- Preserve Halyard's privacy boundary: no prompts, chat text, source code,
  filenames, file contents, terminal output, secrets, or transcripts.

## Non-Goals

- No VS Code extension implementation in this change.
- No automatic Copilot token or cost claim unless public APIs expose it.
- No content capture.
- No productivity score or developer ranking.
- No hosted service.
- No breaking change to existing `ai-sessions.log` records.

## User Stories

- As a VS Code user, I can record Copilot work from the editor without manually
  constructing a terminal command.
- As a Halyard user, I can compare AI work shape across Claude Code, Cursor,
  Gemini CLI, Codex Desktop, and VS Code.
- As a privacy-conscious user, I can prove interaction intensity without
  exposing prompts or code.
- As a technical reviewer, I can inspect the coverage table and know which
  fields are captured, observed, inferred, manual, or unavailable.

## Acceptance Criteria

- PRD and ARD exist for the extension and metadata parity work.
- Specs define the shared metadata field vocabulary.
- Specs define VS Code extension behavior and privacy constraints.
- Specs define collector parity expectations for Claude Code, Cursor, Gemini
  CLI, Codex Desktop, and VS Code.
- Tasks are written before implementation starts.

