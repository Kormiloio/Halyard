# Design: v5.25 — Grok CLI Collector

> **Status: provisional below Phase 0.** Grok's on-disk layout is
> documented by the vendor (`~/.grok/docs/user-guide/`), but
> `~/.grok/sessions/` does not exist yet on the reference machine and
> `active_sessions.json` is `[]`. Field names below come from the vendor
> docs, not from an observed file. Amend this document when the spike
> contradicts it (CLAUDE.md).

## Observed facts (2026-08-09)

Binary `~/.local/bin/grok`; `~/.grok/bin/grok` →
`../downloads/grok-macos-aarch64`. Config `~/.grok/config.toml` is
`[cli] installer = "internal"` — no compat overrides, so **every compat
cell is at its default of `true`**.

Documented session layout (`17-sessions.md`):

```
~/.grok/sessions/<url-encoded-cwd>/<session-id>/
  summary.json        # summary/title, timestamps, model id, message counts
  signals.json        # token usage, tool/turn counters   ← primary source
  updates.jsonl       # ACP conversation + tool-call stream
  chat_history.jsonl  # raw messages         ← never read (non-negotiable 5)
  plan.json, rewind_points.jsonl, feedback.jsonl
  subagents/          # per-subagent meta.json
```

Session ids are UUIDv7 when Grok generates them. Groups are named by
URL-encoding the cwd; when the encoded name exceeds 255 bytes Grok uses a
slug plus hash and records the true path in a `.cwd` file inside the
group. `GROK_HOME` overrides the `~/.grok` base.

Hook events (`10-hooks.md`): `SessionStart`, `UserPromptSubmit`,
`PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `PermissionDenied`,
`Notification`, `Stop`, `StopFailure`, `SessionEnd`, `SubagentStart`,
`SubagentStop`, `PreCompact`, `PostCompact`. `Stop` fires on genuine
completion, not on user interrupt. Default timeout 5s, 600s for `Stop`
gates. All hook failures are fail-open.

## P0 — the contamination fix

**Detection** (`doctor.py`), independent of whether the collector ships:

```
Grok present (~/.grok or the binary on PATH)
  AND halyard hooks present in ~/.claude/settings.json or ~/.cursor/hooks.json
  AND ~/.grok/config.toml lacks [compat.claude] hooks = false
                             / [compat.cursor] hooks = false
  → warning: "Grok will run Halyard's Claude/Cursor hooks and
              mis-attribute Grok sessions"
```

**Remedy**, documented and offered — not applied silently, since it also
disables any legitimate Claude/Cursor-compatible hooks the user wants
under Grok:

```toml
[compat.claude]
hooks = false

[compat.cursor]
hooks = false
```

Note this is the *narrow* toggle: only `hooks`. The sibling cells
(`skills`, `rules`, `agents`, `mcps`) stay on, so Grok keeps reading
`~/.claude/CLAUDE.md` — which is desirable, as that is where the user's
spec-discipline rules live.

**Defence in depth.** Even with compat scanning on, a Grok-originated
invocation must not produce a `claude-code` row. `claude_code.py` and
`cursor.py` should assert the payload actually came from their own
harness (Phase 0 determines the discriminator — an env var, a payload
key, or the absence of `transcript_path`) and exit non-zero-but-fail-open
otherwise. Toggling vendor config is the user's remedy; refusing to write
a wrong row is ours.

## Capture path: native hooks, importer as backfill

Three candidates:

| Path | Verdict |
|---|---|
| Native hooks in `~/.grok/hooks/halyard.json` | **Primary.** Always trusted, no compat borrowing, real-time, mirrors the Claude/Gemini/Cursor design already in this codebase. |
| Session-directory importer | **Secondary.** Backfills pre-install history and repairs missed turns; `signals.json` carries authoritative token counts. |
| External OTEL (`GROK_EXTERNAL_OTEL=1`) | **Rejected for now.** Halyard has an OTLP receiver, so this is tempting, but it is a third writer for the same sessions and its env-var activation is global to the shell. Revisit only if hooks prove to lack token counts. |

Hooks and importer must not double-count: both key on the same Grok
session id, so `job_id = grok:{session_id}` deduplicates across them —
the same pattern `copilot.py` uses for its jsonl/OTEL split
(`copilot:` vs `copilot-otel:` namespaces, unified on session key).

## Collector shape

```python
_GROK_HOME     = Path(os.environ.get("GROK_HOME", Path.home() / ".grok"))
_SESSIONS_DIR  = _GROK_HOME / "sessions"
_HOOKS_FILE    = _GROK_HOME / "hooks" / "halyard.json"
_STATE_FILE    = Path.home() / ".halyard" / "grok-session"
_IMPORTED_STATE = Path.home() / ".halyard" / "grok-imported"
```

- `tool = "grok"`, `job_id = grok:{session_id}`,
  `telemetry_source = "grok-signals"` (hooks) /
  `"grok-sessions"` (importer).
- Hook commands: `grok-session` (SessionStart), `grok-hook` (Stop),
  `grok-fail` (StopFailure) — hidden commands, matching the existing
  `cc-*` / `gc-*` / `cursor-*` naming.
- Resolve the project from the group directory: URL-decode it, or read
  `.cwd` when the hashed-slug fallback is in play. **Do not assume the
  group name is always decodable** — the 255-byte fallback is documented
  and will otherwise misattribute long paths.
- Read `summary.json` and `signals.json` only. Never `chat_history.jsonl`
  or `updates.jsonl`.

## State file: growth-aware from day one

As in v5.24, and for the same reason (v5.2, v5.21, v5.22 all shipped
plain id-set state and all needed a growth fix): `grok-imported` stores
`{session_id → high-water mark}`, and a re-import emits a row only when
the mark advances, superseding the prior row for that `job_id`.

Grok makes this more likely to matter, not less: `/resume`, `--continue`,
and `--fork-session` all mutate an existing session directory in place.
Forks get a new id and a parent reference, so they are new rows; resumes
are growth on the same id.

## Doctor integration

- Grok absent → `SKIPPED`.
- Grok present, no hooks and no captured rows → `warning`, fix
  `halyard install-hook-grok`.
- **Compat contamination** (above) → `warning`, fix = the TOML snippet.
- Captured but newest session mtime materially newer than newest captured
  row → lagging warning, consistent with the claude-code lag check.
- Captured and current → `OK`.

Use a command name in `fix=` that is visible in `halyard --help`.
`doctor.py` currently suggests `install-hook`, `install-cursor-hook`, and
`install-gemini-hook`. These *do* work — they are registered as
`hidden=True` aliases in `cli_hooks.py` — but they do not appear in
`--help`, so a user who copies the fix and then tries to find the command
cannot. Prefer the visible names (`install-hook-claude`,
`install-hook-cursor`, `install-hook-gemini`).

## Testing

- Golden-file: sample `summary.json` + `signals.json` → expected `s` row.
- Idempotence: import twice → one row.
- Growth: resumed session → prior row superseded, not duplicated.
- Fork: `--fork-session` child → a distinct row, parent unchanged.
- **Contamination:** a Grok-shaped hook payload delivered to
  `cc-hook`/`cursor-*` writes **no** row.
- **Attribution:** Claude Code, Cursor, and Grok fixtures side by side →
  three rows, three tools, no duplicates.
- Doctor: absent / unhooked / contaminated / lagging / current.
- Long cwd → hashed-slug group with `.cwd` resolves to the right project.
- v5.23 duplicate canary quiet on a mixed-tool ledger.
- `perf_ceiling` for any timing assertion; no wall-clock literals.
