# v2.52 — Unwired-Tool Detection Nudge

## Problem

Halyard wires AI tools into its ledger only when the user runs
`halyard init` / `halyard setup` (hooks + v2.51 MCP auto-register). It
has no daemon and no background watcher (deliberately). Consequence:
if a user installs a *new* AI tool **after** setup — e.g. installs
Cursor a week later, or starts using Codex — Halyard silently captures
nothing from it and never says so. The user only finds out when they
notice missing sessions in the dashboard, which is exactly the
"data you can't trust" failure mode Halyard exists to prevent.

There is no passive discovery surface today. `halyard doctor` already
diagnoses *configured* tools but does not flag a supported tool that is
**installed but unwired**.

## Goal

Make `halyard doctor` surface supported AI tools that are present on
the machine but not wired into Halyard, with the exact one-line fix —
turning a silent gap into a visible, actionable warning. No daemon, no
new runtime; this is a read-only diagnostic enhancement.

- **Live-hook tools (Claude Code, Cursor, Gemini CLI):** if the binary
  is on PATH but hooks **and** the MCP server are absent, emit a
  `warn` check with fix `halyard setup` (or the specific
  `halyard install-hook-<tool>` / `install-mcp-<tool>`).
- **Codex (import model):** if Codex Desktop session history exists on
  disk but no Codex sessions have been imported, emit a `warn` check
  with fix `halyard import-codex`.
- The dashboard/TUI health surface already reads doctor-style state;
  the new checks flow through the existing `DoctorReport` so they
  appear there too with no extra wiring.

## Constraints honored

- **Read-only / no daemon.** Detection is on-demand inside
  `build_doctor_report()` — runs only when the user invokes `doctor`
  (or a surface that calls it). Nothing watches the system.
- **No false alarms.** A tool wired via *either* hooks or MCP for its
  scope is "wired enough" not to nag; the nudge fires only when a
  detected tool has *no* Halyard integration at all.
- **Reuse, don't duplicate.** Detection uses the same
  `shutil.which`/config-introspection helpers the installers and
  existing `_hook_checks` use; no parallel detection logic.

## Non-goals

- No auto-install on detection (that would need a prompt/daemon; the
  whole point of the no-daemon design is the user runs setup).
- No new supported tools — only the four Halyard already knows
  (Claude Code, Cursor, Gemini CLI, Codex).
- No notification/telemetry channel — the signal is the doctor report
  and the health surfaces that already render it.

## Out of scope

A general "watch for newly installed tools and offer to wire them"
interactive flow — explicitly rejected (daemon/UX cost) in favor of
this passive, on-demand diagnostic.
