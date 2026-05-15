# PRD: VS Code Extension and Metadata Parity

**Status:** Proposed
**Date:** May 14, 2026
**Companion ARD:** `docs/ARD-vscode-extension-and-metadata-parity.md`
**OpenSpec change:** `openspec/changes/archive/2026-05-14-v2.32-vscode-extension-metadata-parity/`

---

## Summary

Halyard should add a VS Code extension and upgrade every collector toward a
shared metadata vocabulary for AI-assisted work. The goal is not content
capture. The goal is interaction shape: how much human steering, tool activity,
and outcome movement was required to complete a unit of work.

The extension should make VS Code/Copilot capture easy and visible. The
cross-tool metadata work should make Claude Code, Cursor, Gemini CLI, Codex
Desktop, and VS Code comparable without pretending they expose identical data.

## Problem

Halyard already captures time, tool, model, token, cost, project, and git
metadata across several tools. Rich telemetry exists for some collectors,
especially Gemini CLI, but the metadata is uneven:

- VS Code/Copilot is manual and awkward.
- Claude Code and Cursor capture strong baseline metadata but limited
  interaction counts.
- Gemini CLI has the richest operational telemetry today.
- Codex Desktop imports token snapshots but limited interaction shape.
- Reports cannot yet answer, consistently across tools, "how much human
  interaction was needed to complete this work?"

Technical users will trust Halyard more if it is explicit about what is
captured, what is unavailable, and what is inferred.

## Product Thesis

Halyard should become the privacy-preserving record of AI work shape. It should
tell a developer, client, or team lead:

- how many AI sessions happened;
- which tools and models were involved;
- how many interaction turns or prompts were needed when available;
- how much tool activity happened;
- how much code/outcome movement happened;
- how much human time surrounded the AI work;
- which data is measured, estimated, inferred, or unavailable.

It should do this without storing prompts, chat text, source code, filenames,
file contents, terminal output, or transcripts.

## Goals

- Ship a VS Code extension that uses the installed Halyard CLI as the local
  ledger writer.
- Make VS Code/Copilot capture one-click from the editor.
- Show Halyard status in VS Code: current scope, active timer, and last capture.
- Add shared optional metadata fields for interaction counts and outcome shape.
- Upgrade every collector to populate the shared fields when the tool exposes
  them.
- Treat missing telemetry as unavailable, not zero.
- Preserve the local-first, plain-text `ai-sessions.log` source of truth.
- Keep privacy language precise and durable.

## Non-Goals

- No prompt, chat text, source-code, transcript, file-content, or filename
  capture.
- No hidden background scraping of VS Code or Copilot state.
- No productivity scoring, developer ranking, or surveillance language.
- No cloud account or hosted service requirement.
- No claim that Copilot exposes per-session token or cost data unless a public
  API actually provides it.
- No SQLite-only metadata that cannot be reconstructed from plain text.

## Audiences

### Individual developer

Wants to include VS Code/Copilot work in Halyard without leaving the editor and
without leaking private work.

### Freelancer or consultant

Wants client-safe evidence showing AI involvement and human steering intensity,
not raw prompts or code.

### Small AI shop or technical lead

Wants comparable metadata across tools so project reports can distinguish
low-touch AI assists from heavily guided sessions.

## Primary Experience

The user installs the extension and points it at the local `halyard` executable.
The status bar shows whether Halyard sees a project or hub. The user can start
or stop a VS Code AI work block from the command palette or status bar.

Suggested VS Code commands:

- `Halyard: Start AI Work`
- `Halyard: Record AI Session`
- `Halyard: Stop and Record AI Work`
- `Halyard: Open Dashboard`
- `Halyard: Show Current Scope`

The extension shells out to the Halyard CLI. The Python package remains the
authority for parsing, attribution, log writing, pricing, and reports.

## Metadata To Capture

All fields are optional. Each collector writes only what it can observe without
content capture.

Baseline fields:

- `start`
- `end`
- `tool`
- `model`
- `input_tokens`
- `output_tokens`
- `cache_read`
- `cache_write`
- `cost_usd`
- `project`
- `branch`
- `source`
- `attr_method`
- `billing`

Interaction fields:

- `interaction_count`
- `user_message_count`
- `assistant_message_count`
- `prompt_count`
- `accepted_suggestion_count`
- `rejected_suggestion_count`
- `tool_calls`
- `tool_errors`

Timing fields:

- `wall_seconds`
- `agent_active_seconds`
- `human_active_seconds`
- `idle_seconds`

Outcome fields:

- `commit_count`
- `code_added`
- `code_removed`
- `files_touched_count`
- `test_run_count`
- `test_status`
- `build_status`

Quality and provenance fields:

- `tokens_available`
- `interaction_data_available`
- `outcome_data_available`
- `telemetry_source`
- `telemetry_trust`

## Tool Expectations

### Claude Code

Populate tokens, cache, model, branch, commit count, and code delta as today.
Add interaction counts from hook payloads or transcript event structure only
when counts can be derived without storing content.

### Cursor

Populate workspace, project, branch, commit count, code delta, tokens when
present, and any interaction counts exposed in the hook payload. Cursor
subscription cost remains allocated or credit-based unless per-session cost is
available.

### Gemini CLI

Continue using hooks plus history enrichment. Normalize existing tool call,
tool error, wall time, code delta, model breakdown, and resume metadata into
the shared vocabulary. Add interaction/message counts when available.

### Codex Desktop

Continue importing JSONL session files. Add interaction counts from event types
and token snapshots when available. Store counts only, never message text.

### VS Code / GitHub Copilot

Start with extension-observed metadata: elapsed time, workspace scope, branch,
manual model label, prompt or interaction count when the extension can observe
the command/workflow, accepted/rejected suggestion counts when available through
public APIs, code delta from git, file count without filenames, and test/build
status when user invokes extension commands. Mark unavailable fields honestly.

## Reporting Requirements

Reports and dashboards should be able to answer:

- How many sessions happened?
- How many interactions were observed?
- Which tools/models carried the work?
- Which sessions have unavailable interaction data?
- What was the ratio of human time to AI session count?
- Which projects required more steering?
- Which results are captured, inferred, allocated, or unavailable?

The UI must avoid ranking people. Phrase derived signals as work-shape or
review signals, not performance judgment.

## Privacy Promise

Halyard records metadata about AI-assisted work: time, tool, model, token
counts, interaction counts, project, branch, cost, and outcome signals. Halyard
does not record prompts, chat text, source code, filenames, file contents,
terminal output, secrets, or transcripts.

Collectors may temporarily read local structured tool files to count events or
aggregate token metadata. They must not persist raw content from those files.

## Acceptance Criteria

- A user can install the VS Code extension and record a VS Code AI work block
  into `ai-sessions.log`.
- VS Code records use the shared metadata vocabulary where possible.
- Existing collectors continue to parse old logs and omit unavailable fields.
- Each collector has a documented metadata coverage table.
- Reports distinguish zero counts from unavailable counts.
- Tests prove that no prompt, code, filename, transcript, or terminal output is
  serialized by the new metadata fields.

