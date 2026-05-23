# Proposal: v3.10 — doctor capture-coverage canary

## Why this exists

The Gemini collector silently stopped recording on 2026-05-07 and nobody
noticed for 16 days. `halyard doctor` showed **"Gemini CLI hooks installed
OK"** the entire time — because it only checks that hooks are *configured*,
not that data is *flowing*. The v2.59 collector-drift canary couldn't catch it
either: it keys on the last N *rows* for a tool, and a tool that produces
**zero** rows has nothing to analyze. So a collector that fully breaks is
invisible to every existing check.

## What changes

A new `_capture_coverage_checks` in `doctor.py` compares each live-capture
tool's **newest on-disk session file** against its **last captured ledger
row**. If the tool keeps writing session files while the ledger stalls, capture
silently broke.

- Probed tools: `claude-code` (`~/.claude/projects/*/*.jsonl`) and `gemini-cli`
  (`gemini_history.find_all_session_files()`) — the live-capture tools with a
  cheap on-disk source the collector already reads.
- Fires only with a **baseline** (≥1 captured row), so a never-used tool can't
  false-positive.
- `_COVERAGE_LAG_DAYS = 2` grace absorbs normal lag (an in-flight turn, an idle
  gap) so only a real, sustained break trips it.
- `warning`, never `error` (exit-code contract preserved); detection-only (no
  upstream formats parsed); flows through `DoctorReport`, so `halyard status`
  and the health surfaces inherit it.

Importer tools (codex/copilot) are intentionally **not** probed here — their
"history on disk but not imported" case is already the v2.52 unwired-import
nudge, and they legitimately lag the ledger between imports.

## Why this is the right check

It is false-positive-resistant by construction: it fires only when there is
literal on-disk evidence (a newer session file) that the tool ran but the
ledger didn't record it. Applied to the actual outage, it would have flagged
Gemini within ~2 days instead of 16, and it now also guards Claude Code.

## Success criteria

- Stale ledger + fresh disk → one `coverage.<tool>` warning.
- Fresh ledger, or no baseline, or lag within grace → no warning.
- Live `halyard doctor` shows no coverage warning once Gemini is backfilled and
  Claude Code is current. ruff/mypy clean; suite green.
