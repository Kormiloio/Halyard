# Proposal: v5.24 — Antigravity Collector

## Why this exists

Antigravity is Google's agentic IDE. It is installed on at least one
maintainer machine (`/Applications/Antigravity.app`, first run
2026-08-09) and produces exactly the kind of high-volume agentic work
Halyard exists to capture — yet Halyard has no collector for it. Sessions
run there are invisible to the ledger.

Two things make this more than "one more collector":

**The docs already conflate it with Gemini CLI.**
`docs/PRD-developer-experience.md:23` describes the design advisors as
"Claude CLI, Cursor, and Antigravity (Gemini CLI)", treating Antigravity
as a synonym for Gemini CLI. They are different products: Gemini CLI is a
terminal agent installed via Homebrew (`gemini-cli` 0.46.0); Antigravity
is a desktop IDE. The parenthetical is wrong and must be corrected, or
future contributors will assume the existing Gemini collectors already
cover it.

**They share a state root, which is a live double-count hazard.**
Antigravity stores state under `~/.gemini/antigravity/` — inside the same
`~/.gemini/` tree that `collectors/gemini_history.py` already walks
(`~/.gemini/tmp`, `~/.gemini/history`). Any collector added here has to be
explicit about path ownership, or the two will cross-contaminate. This
repo has already shipped three separate duplicate-row defects (v5.2,
v5.21, v5.22) and a doctor canary for them in v5.23; adding a second
reader under a shared root without deciding ownership invites a fourth.

`doctor` also has no Antigravity row, so the gap is currently silent —
the same failure mode as VS Code, which has an `install-vscode-otel`
command but no readiness check.

## What changes

- **Phase 0 spike — done (2026-08-09).** A real conversation was run and
  the format inspected; see `design.md`. Headline results: the
  `conversations/*.db` store is SQLite wrapping undocumented binary
  protobuf and is **rejected as a source**; a clean JSONL transcript
  exists and is the real target; Antigravity **does** have a documented
  hook surface; and **no token, model, or cost data is available
  anywhere**.
- **New collector:** `src/halyard/collectors/antigravity.py`.
- **Hooks:** `halyard install-hook-antigravity`, writing a `Stop` /
  `PostInvocation` handler to the customization root's `hooks.json`.
- **Importer:** `halyard import-antigravity` (`--dry-run`, `--all`),
  matching the Codex/Gemini/Copilot importer contract.
- **Wire into `import-all`** so the scheduled LaunchAgent picks it up.
- **Doctor row:** Antigravity presence + capture readiness, plus a
  lagging-capture check consistent with the existing per-tool checks.
- **Path ownership:** `gemini_history` explicitly excludes
  `~/.gemini/antigravity/`; the new collector reads only that subtree.
- **Docs:** correct the Antigravity/Gemini CLI conflation in
  `docs/PRD-developer-experience.md`; add Antigravity to the supported
  tool matrix in `README.md`.

## User stories

- **As an Antigravity user**, I want my agent conversations recorded in
  `ai-sessions.log` so IDE work is not missing from invoices and
  proof-of-work artifacts.
- **As a user of both Gemini CLI and Antigravity**, I want each attributed
  to the right tool, and counted exactly once.
- **As a maintainer**, I want `halyard doctor` to tell me Antigravity is
  present but uncaptured, rather than staying silent.

## Success criteria

- Running a conversation in Antigravity, then `halyard import-antigravity`,
  appends a row with `tool=antigravity` and a correct model, token, and
  wall-time reading.
- Re-running the importer appends nothing (no growth re-import defect —
  the v5.2 / v5.21 / v5.22 class).
- With both Gemini CLI and Antigravity active, no session appears twice
  and neither collector claims the other's files.
- `halyard doctor` shows an Antigravity row: green when captured, warning
  when the app is present but unwired.
- v5.23's ledger duplicate canary stays quiet across a mixed-tool run.

## Out of scope

- OTLP capture. No OTLP exporter is documented for Antigravity.
- Per-tool `PreToolUse` / `PostToolUse` hook events — too high volume;
  the transcript already carries tool-call counts by type.
- Prompt or conversation-content capture — barred by non-negotiable 5.
- Grok CLI, also unsupported and also newly installed. Same collector
  shape, different vendor and format; it deserves its own changeset
  rather than being smuggled in here.

## Risks and trade-offs

- **No spend data — confirmed, and the biggest trade-off here.** Neither
  the transcript nor the protobuf blobs carry token counts, and the hook
  payload reports `modelName: "auto"`. Antigravity rows will carry real
  wall time and interaction counts but **zero tokens and zero cost**,
  stamped `telemetry_trust=inferred`. Budget and spend totals therefore
  under-count while Antigravity is in use, and every surface that shows
  spend must say so rather than let a zero read as "free work". If that
  trade-off is unacceptable, the honest alternative is to not ship this
  collector at all — partial capture that silently deflates spend is
  worse than no capture.
- **Rejected data source.** The `conversations/*.db` protobuf store may
  well contain richer data, but with no published schema, parsing it is
  fragile against silent vendor revs. Revisit only if the vendor
  publishes a schema.
- **Undocumented, unstable surface.** A vendor-internal directory layout
  may change without notice — the same standing risk accepted for the
  Windsurf and Copilot collectors.
- **Shared root.** Covered above; the mitigation is explicit path
  ownership plus a regression test asserting neither collector reads the
  other's tree.
