# Proposal: v5.25 — Grok CLI Collector

## Why this exists

Grok CLI (xAI) is installed on a maintainer machine (`~/.local/bin/grok`,
`~/.grok/`, first run 2026-08-09) and Halyard has no collector for it.
Unlike Antigravity (v5.24), the gap here is not merely missing coverage —
**Halyard's existing hooks already fire under Grok, and attribute Grok's
work to the wrong tool.**

### The live defect

Grok's documented hook discovery merges these global sources, all
"Always" trusted:

| Path | Notes |
|---|---|
| `~/.grok/hooks/*.json` | Grok-native |
| `~/.claude/settings.json` | Claude Code compatibility, **on by default** |
| `~/.cursor/hooks.json` | Cursor compatibility, **on by default** |

`[compat.claude] hooks` and `[compat.cursor] hooks` both default to
`true`. Halyard installs into exactly those two files
(`install-hook-claude`, `install-hook-cursor`). Grok also accepts Cursor's
camelCase event names, so `~/.cursor/hooks.json` loads unchanged, and its
`Stop` / `UserPromptSubmit` events line up with the ones Halyard registers
for Claude Code.

The consequence: a Grok session invokes `halyard cc-hook` and the Cursor
hook commands. Grok's work is recorded as `tool=claude-code` or
`tool=cursor` — and plausibly both, since the two sources merge rather
than override. That is silent mis-attribution in a ledger whose entire
purpose is trustworthy attribution, and it lands in invoices.

This violates non-negotiable 6 (trust labels over fake certainty): the
rows are stamped `telemetry_trust=observed` while naming the wrong tool.

### Why the existing collectors won't simply fail safely

`collectors/claude_code.py` keys off the `transcript_path` in the hook
payload. Grok's payload shape is its own; the collector may no-op, may
error (hooks are fail-open, so the user sees nothing), or may find enough
to write a wrong-tool row. All three outcomes are bad, and which one
occurs is currently unverified — a Phase 0 question.

## What changes

- **P0 — stop the contamination.** Document and ship the
  `[compat.claude] hooks = false` / `[compat.cursor] hooks = false`
  remedy in `~/.grok/config.toml`, and make `halyard doctor` detect the
  hazard: Grok present + Halyard hooks in `~/.claude/settings.json` or
  `~/.cursor/hooks.json` + compat not disabled → warning.
- **New collector:** `src/halyard/collectors/grok_cli.py`.
- **Native hooks:** `halyard install-hook-grok`, writing to
  `~/.grok/hooks/halyard.json` (Grok-native, always trusted, no
  compat borrowing). Events: `SessionStart`, `UserPromptSubmit`, `Stop`,
  plus `StopFailure` so API-error turns are not silently dropped.
- **Importer:** `halyard import-grok` (`--dry-run`, `--all`) reading
  `~/.grok/sessions/`, honouring `GROK_HOME`.
- **Wire into `import-all`.**
- **Doctor rows:** Grok capture readiness, plus the compat-contamination
  check above.
- **Pricing:** `pricing.py` carries only `grok-3` and `grok-3-mini`.
  Refresh against the models Grok CLI actually reports.
- **Docs:** add Grok to the supported-tool matrix in `README.md`.

## User stories

- **As a Grok CLI user**, I want my sessions captured as `tool=grok`, not
  silently mislabelled as Claude Code or Cursor.
- **As someone billing clients from this ledger**, I want to trust that a
  row naming a tool actually came from that tool.
- **As a maintainer**, I want `doctor` to catch cross-harness hook
  borrowing rather than let it corrupt data silently.

## Success criteria

- A Grok session produces exactly one row, `tool=grok`, with real token
  counts and model id.
- With Claude Code, Cursor, and Grok all installed and all hooked, each
  tool's sessions are attributed to itself and counted once.
- `doctor` warns when Grok is present and compat hook-scanning would
  borrow Halyard's Claude/Cursor hooks, with a fix that resolves it.
- Re-running `import-grok` appends nothing (no growth re-import defect).
- v5.23's ledger duplicate canary stays quiet across a mixed-tool run.

## Out of scope

- Grok's `PreToolUse` / `PostToolUse` per-tool events — too high volume;
  turn-level counters in `signals.json` already cover tool counts.
- Subagent sessions as distinct ledger rows. Grok writes child sessions
  into the normal tree; whether they merit their own rows is a follow-up.
- Prompt or conversation-content capture — barred by non-negotiable 5.
  `chat_history.jsonl` and `updates.jsonl` are never read for content.

## Risks and trade-offs

- **No session sample yet.** `~/.grok/sessions/` does not exist and
  `active_sessions.json` is `[]` — the app has not been run. Field-level
  layout is documented (below) but unverified.
- **Three possible capture paths.** Native hooks, session-directory
  import, and Grok's external OTEL stream (`GROK_EXTERNAL_OTEL=1` with an
  OTLP endpoint, which Halyard's existing receiver could accept). Picking
  more than one risks double-counting; `design.md` chooses.
- **Compat toggles are the vendor's, not ours.** Disabling
  `[compat.claude] hooks` means any *legitimate* Claude-compatible hook
  the user wants under Grok also stops. That trade-off belongs to the
  user, so the remedy is documented and recommended, not silently
  applied.
- **Undocumented stability.** Session-directory layout is vendor-internal
  and may change — the standing risk accepted for Windsurf and Copilot.
