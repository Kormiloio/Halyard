# Proposal: v3.5 — Claude Code client-surface tag (CLI vs. desktop)

Status: **shipped.**

## Why this exists

Claude Code is sold as a single product but ships through several
launchers — terminal CLI, macOS/Windows desktop app, IDE extensions,
and the web app at claude.ai/code. Anthropic treats them as one tool;
Halyard does the same and tags every session
`tool="claude-code"` ([src/halyard/collectors/claude_code.py:240](src/halyard/collectors/claude_code.py:240)).
For most analytics that is correct.

For the owner — who is a daily user of *both* the CLI and the desktop
app — it isn't. The dashboard cannot answer "which surface do I lean
on for what kind of work?" because every session collapses into a
single `claude-code` bucket. v3.4 added MCP-server inventory, but a
desktop-only MCP server and a CLI-only one are indistinguishable in
the report today.

The Stop-hook payload and transcript JSONL are byte-identical across
surfaces (same writer in Claude Code itself), so the surface signal
*cannot* come from the payload — it has to come from the hook
process's own environment at the moment `halyard cc-hook` runs.

## Goal

Add a single optional advisory tag — `client_surface` — to every
Claude Code `AiSession`, with one of:

- `cli` — terminal launcher (interactive shell, ssh)
- `desktop` — bundled desktop app launcher
- `ide` — VS Code / JetBrains extension launcher (deferred-detect; ok to leave `None` if ambiguous)
- `unknown` — surface detection inconclusive

Then surface it as a sub-bucket in the dashboard, reports, and the TUI
— alongside `tool` rather than replacing it. The existing `tool` field
stays `"claude-code"` so every shipped metric, view, and external
consumer is unaffected.

## Non-goals

- **Not** splitting `tool` itself. `tool="claude-code"` stays the
  canonical identifier; v3.5 only adds a sub-tag.
- **Not** a hard, audited classification. This is an *advisory*
  heuristic — the spec must label it as such anywhere it is rendered,
  same pattern v2.32 uses for honest labelling.
- **Not** a privacy boundary change. The detector reads env vars and
  parent-process names only; it never reads prompts, code, or
  transcript text beyond what claude_code.py already reads.
- **Not** retroactive. Existing log lines without the tag stay
  `client_surface=None`; no backfill, no migration.

## Constraints honored

- **Unavailable is not zero.** Surface unknown → `client_surface=None`
  (or `"unknown"` if we want it explicit in reports — design decides),
  never a fabricated guess.
- **v2.75 extensible log contract.** New token rides through the
  existing key=value parser; old Halyards parse new lines without
  loss.
- **Backward compatible.** Every `tool="claude-code"` filter keeps
  working; the new field is purely additive.
- **No new schema migration.** Single nullable column on
  `AiSession` mirrors how v3.4 added `mcp_servers_used`.

## Risks and tradeoffs

- **Heuristic, not authoritative.** tmux, ssh forwarding, IDE
  terminals, screen sharers, and remote dev containers can all blur
  the signal. The proposal accepts this — the tag is advisory and
  honest about its trust level.
- **Surfaces could change without notice.** If Anthropic renames
  `__CFBundleIdentifier`, our detection silently falls back to
  `unknown`. The v2.59 drift canary catches the regression — same
  contract as every other collector field.
- **No upstream API for this.** If Anthropic later exposes a
  first-class client identifier in the Stop payload, we drop the
  heuristic and read the field. The proposal anticipates that swap.
- **Privacy.** Env vars can in principle contain secrets. The
  detector reads only the small named subset above; it never logs the
  full environment, never persists raw env values to the session log,
  and only writes the bucketed string (`cli`/`desktop`/`ide`/`unknown`).
-path hole.

`design.md` and `tasks.md` are written in this changeset as the
*intended* shape, but every empirical claim in them is flagged
"pending Phase-0" and will be edited against the spike output before
any code lands.
