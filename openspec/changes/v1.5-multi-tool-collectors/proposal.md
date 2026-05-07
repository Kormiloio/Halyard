# Proposal: v1.5 — Multi-Tool Collectors and Ambient Capture

## Why this change

v1 made one bet: Claude Code is the beachhead. It worked — the hook collector,
the log schema, and `halyard report` shipped. But the bet was narrower than
the reality of how developers work.

A developer's typical day might look like:

- Open Cursor to navigate a large codebase
- Switch to Claude Code for a focused refactor
- Ask Gemini CLI a quick architecture question
- Run Codex to scaffold a new module

In v1, three of those four sessions are invisible. `ai-sessions.log` shows
Claude Code only. The cost picture is wrong. The project attribution is
incomplete. The promise of "know what AI actually costs on each engagement"
fails the moment the developer reaches for a second tool.

v1's proposal acknowledged this — it included an "API proxy collector (the
unlock)" as the path to multi-tool capture. That approach was reconsidered.

### Why not the API proxy

The API proxy is architecturally elegant: intercept `api.anthropic.com` and
`api.openai.com`, log usage transparently, forward the request. No per-tool
integration needed.

In practice it has significant problems:

1. **TLS interception.** A proxy that captures HTTPS traffic requires either a
   man-in-the-middle cert installed in the system trust store, or every tool
   trusting the proxy cert explicitly. Both create legitimate security concerns
   for enterprise users.

2. **Tool trust boundaries.** Tools like Cursor and Gemini CLI go out of their
   way to avoid system-level proxies for exactly this reason. Getting reliable
   coverage would require per-tool proxy config anyway.

3. **Latency on every call.** Every API call goes through the proxy. A buggy
   or slow proxy silently degrades the developer's working environment.

4. **It turns out the tools already have hooks.** Cursor, Gemini CLI, and
   Claude Code all expose hook systems designed for exactly this use case.
   Codex writes JSONL session logs. The data is already there — we just needed
   collectors that speak each tool's native language.

### The hook-native approach

Each AI tool exposes session events in its own way:

- **Claude Code:** `UserPromptSubmit` and `Stop` hooks, JSON payload on stdin
- **Cursor:** `beforeSubmitPrompt` and `stop` hooks, same structure
- **Gemini CLI:** `SessionStart`, `AfterModel`, `AfterAgent` hooks, JSON on stdin
- **Codex Desktop:** JSONL session files in `~/.codex/sessions/`

v1.5 builds a native collector for each tool. The result is richer than the
proxy approach: we get workspace context, model routing decisions, and
tool-specific metadata that a transparent proxy would not capture.

## The ambient capture problem

Even with four collectors working correctly, sessions were still being
silently dropped whenever the hook fired outside a directory tree containing
a `halyard.toml`. The collector would call `find_project_dir()`, get `None`,
and return 0 — the session gone.

This was especially painful for Claude Code and Cursor, which are global tools.
A developer working in `/projects/acme-auth` — a directory Halyard knows
nothing about — generates real sessions with real costs, and they all
disappear.

v1.5 solves this with two mechanisms that work together:

**The hub:** A single designated Halyard project directory that acts as the
global fallback. Any session that doesn't match a local `halyard.toml` tree
goes here. The developer runs `halyard init --hub` once and stops losing data.

**Git inference:** When a session lands in the hub, Halyard runs
`git remote get-url origin` in the working directory to identify the repo.
Explicit mappings in `~/.halyard/repos.toml` translate remotes to project
slugs. Unknown repos get a `git/<repo-name>` auto-slug that the developer can
promote later with `halyard link-repo`.

Together these mean: configure once, never lose a session again.

## What this change does

1. **Four new collectors:** Codex (JSONL importer), Cursor (hook), Gemini CLI
   (three-hook pipeline with per-turn state accumulation), plus hardening of
   the Claude Code collector.

2. **Hub and ambient capture:** `hub.py` + `~/.halyard/hub` pointer. All four
   collectors fall back to the hub when no local project matches.

3. **Git-based project inference:** `git_context.py`. Resolves repo remote to
   project slug via explicit mapping or auto-slug. Also captures git branch
   as `tags=branch:<name>` on every session.

4. **Gemini cost accuracy:** `billing=api`, `calculate_cost()`, and
   `cachedContentTokenCount` extraction so Gemini sessions carry accurate
   cost data instead of hardcoded `0.0`.

5. **Duplicate suppression:** Claude Code's `Stop` hook now detects
   `cursor_version` in the payload and skips — Cursor fires Claude Code hooks
   internally, so without this guard every Cursor session generates two records.

## What this change does NOT do

- No cloud sync. Sessions still go to local `ai-sessions.log` files.
- No OpenAI/DeepSeek/Grok CLI collectors (those are v2 targets).
- No proxy-based capture (not needed; hook coverage is sufficient for the
  tools in scope here).
- No budget enforcement or alert system (v2 target).
- No changes to the `ai-sessions.log` schema — existing parsers are unaffected.

## Success criteria

- A developer using Claude Code, Cursor, Gemini CLI, and Codex in the same
  day sees all four tools represented in `ai-sessions.log`.
- Sessions from any directory — whether or not it contains `halyard.toml` —
  land in the hub log, with `project=` auto-populated from git.
- `halyard hub` shows the hub path and session count. `halyard link-repo`
  maps a repo in under ten seconds.
- Gemini sessions show non-zero `cost_usd` when a known model is in use.
- The `cursor_version` guard prevents double-recording for Cursor users who
  also have global Claude Code hooks installed.
