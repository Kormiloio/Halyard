# Proposal: v3.15 — Coverage canary for Cursor and Windsurf

## Why this exists

The capture-coverage canary (`halyard doctor`, v3.10/v3.13) is the safety net that
turns a *silent* capture break into a visible warning within a couple of days —
the thing that was missing during the 16-day Gemini outage. But it only watches
**4 of the 7 supported tools**:

```python
_COVERAGE_TOOLS = ("claude-code", "gemini-cli", "github-copilot", "codex")
```

**Cursor and Windsurf are blind spots.** Their hooks may be installed and firing,
but if a hook silently stops (a config wipe, a Cursor version that drops hook
support, a payload-shape change), nothing warns the user — exactly the failure
class the canary exists to catch, just for the two tools it doesn't cover.

## What the investigation found

Unlike the four covered tools, **Cursor and Windsurf do not write enumerable
per-session files**:

- **Cursor** keeps chat/composer state in SQLite (`state.vscdb` under
  `globalStorage` and each `workspaceStorage/<id>/`).
- **Windsurf** keeps Cascade (agent) state under `~/.codeium/windsurf/`
  (`cascade/`, a `database/` store).

Parsing those stores to extract per-session timestamps would re-introduce exactly
the fragile, undocumented-format scraping v3.12 was built to escape. So this
change deliberately does **not** parse them.

## What changes

- **Extend the existing canary mechanism to Cursor and Windsurf using coarse
  storage *mtimes* only** — never schema parsing:
  - Cursor → newest mtime among `…/Cursor/User/**/state.vscdb`.
  - Windsurf → newest mtime under `~/.codeium/windsurf/cascade/`.
- Because a directory/db mtime is a noisier "the app was active" signal than a
  per-session file (it can move when the user only browses code), these two tools
  get a **wider grace** than the file-precise tools and a **best-effort,
  honestly-worded warning** that names the uncertainty ("storage shows activity
  newer than the last capture; if you used the AI features, the hook may not be
  firing").
- `warning` only, baseline-gated (≥1 captured row, so a never-used tool can't
  false-positive), flows through `DoctorReport` like every other check — so the
  dashboard/TUI health surfaces inherit it.

## Honest limitations (stated, not hidden)

- This is a **coarse** signal. It can miss a break if the user keeps using Cursor
  in a way that doesn't move `state.vscdb` much, and it can theoretically
  false-positive if the user browses code in Cursor for days without using AI.
  The wider grace + baseline gate + explicit wording keep that low; the detail
  text tells the user how to interpret it.
- It is **not** a precise per-session reconciliation (the four file-based tools
  still get the tighter check). A precise Cursor/Windsurf canary would require
  parsing their internal stores — rejected on the project's anti-fragility
  principle.

## Success criteria

- With Cursor unused since before its last capture (the current real state), the
  canary reports **no** Cursor warning — confirming "not broken, just unused,"
  not a false alarm.
- A Cursor/Windsurf session newer than the last capture by more than the coarse
  grace produces a `warning` with the one-line fix.
- A never-captured tool produces nothing. ruff/mypy/full suite green.
