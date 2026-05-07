# Proposal: v0.2 — AI Agent Loop

## The Problem
Currently, `halyard log` uses a simple `local` provider that relies on hardcoded string matching (e.g., if "today" is in the query, filter by today). This is brittle and cannot answer complex questions like "What did I work on this week, and how much did Claude cost vs Cursor?" or "Summarize the work I did on the auth project."

## The Solution
Implement the full Anthropic SDK-backed agent loop for `halyard log --agent claude`.
Claude will act as a reasoning engine over local Halyard data. Instead of raw file access, Claude will be provided with strict schema tools (e.g., `read_sessions`, `summarize_by_project`, `read_timeclock`) to fetch data.

This separates the reasoning (Claude) from the data layer (Halyard local files), maintaining Halyard's position as a provider-neutral intelligence tool.

## Scope
- Add `anthropic` SDK integration.
- Define Claude SDK tools for reading session data and summaries.
- Implement the `claude` provider in `log_agent.py` to dispatch tools, collect results, and generate the final answer.
- Support API keys via system environment variables (`ANTHROPIC_API_KEY`).
