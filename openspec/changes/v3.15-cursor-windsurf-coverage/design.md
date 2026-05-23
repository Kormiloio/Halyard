# Design: v3.15 — Cursor/Windsurf coverage canary

## Reuse the existing mechanism, add a coarse tier

The v3.10 canary already has the right shape: `_newest_disk_activity(tool)` →
newest on-disk mtime; `_capture_coverage_checks` compares it to the last captured
row and warns past a grace, baseline-gated. v3.15 adds Cursor and Windsurf to
that machinery with two deliberate differences driven by their storage shape.

### 1. Storage mtime sources (no schema parsing)

Extend `_newest_disk_activity`:

- `cursor` → newest mtime among
  `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` and
  `~/Library/Application Support/Cursor/User/workspaceStorage/*/state.vscdb`.
- `windsurf` → newest mtime among files under `~/.codeium/windsurf/cascade/`.

These are the chat/agent stores. We read only `stat().st_mtime` — never the file
contents — so a vendor schema change cannot break this (it would just shift an
mtime, which is exactly the signal we want).

### 2. A wider grace for coarse signals

A per-session file moves only when a session is written. A SQLite/db mtime can
move for incidental reasons (opening a workspace, indexing), so it is noisier.
To keep false positives low we give these tools a larger grace than the
file-precise tools:

- `_COVERAGE_LAG_DAYS = 2` (unchanged) for claude-code/gemini-cli/github-copilot/codex.
- `_COVERAGE_LAG_DAYS_COARSE = 4` for cursor/windsurf.

Implementation: a second tuple `_COVERAGE_TOOLS_COARSE = ("cursor", "windsurf")`
and a small parameterisation of the existing loop (grace + a `coarse` flag that
selects the warning wording). The baseline gate (≥1 captured row) and
`warning`-only contract are unchanged.

### 3. Honest wording

The coarse warning detail says, in effect: "Cursor storage changed more recently
than the last captured session — if you used Cursor's AI features, the hook may
not be firing; if you only browsed code, ignore." Fix: `halyard install-hook-cursor`
/ `install-hook-windsurf`. This converts a *silent* blind spot into a *visible,
honestly-qualified* signal — the trust goal — without pretending to a precision
the source can't support.

## Why not parse the stores for precise timestamps

Cursor's composer history and Windsurf's Cascade transcripts live inside their
SQLite/leveldb stores. Extracting per-session timestamps would mean decoding an
undocumented, version-specific schema — the exact fragility class that caused the
Gemini and Copilot outages and that v3.12 (OTel) was created to escape. A coarse
mtime that can never crash on a format change is the principled choice here; the
four tools that *do* expose enumerable session files keep the tighter check.

## Verification

Unit tests drive `_capture_coverage_checks` with a monkeypatched
`_newest_disk_activity` so they assert the policy, not the filesystem:
- cursor disk older than capture → no warning (the current real state);
- cursor disk newer than capture beyond the coarse grace → warning;
- within grace → no warning;
- no captured baseline → no warning;
- a file-precise tool still uses the 2-day grace (no regression).
