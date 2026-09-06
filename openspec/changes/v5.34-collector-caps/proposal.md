# v5.34 — The whole-file cap that silently dropped Codex rollouts was everywhere

## Why

v5.32 fixed a 25 MB whole-file cap that made large Codex rollouts
permanently uncapturable, and recorded the same shape in three more
collectors as out of scope: "only Codex is demonstrably losing data here."

It is no longer only Codex. `halyard doctor` reports:

```
WARNING Copilot (unwired)  GitHub Copilot history on disk but none imported
```

and `copilot.py:221` carried `if path.stat().st_size > 50 * 1024 * 1024`
directly above a streaming read. On the machine that found this:

```
  4.5 MB  ok
  0.8 MB  ok
135.9 MB  OVER CAP — silently skipped
```

`halyard import-copilot` found 2 sessions and silently dropped the third.
Nothing logged it. The user's only signal was doctor saying Copilot history
existed but was unimported — with no hint that importing could not fix it.

## The defect, precisely

Every one of these readers streams line by line. Peak memory is the longest
*line*, not the file. A whole-file size cap therefore bounds nothing about
resource use; it only sets the size at which a session silently becomes
uncapturable — and it fails exactly where it costs most, because short
sessions import fine while long agentic runs disappear.

Four sites, and they are not identical:

| collector | read | the cap |
|---|---|---|
| `copilot.py:221` | streams | spurious — dropped a 135.9 MB chat |
| `claude_code.py:765` | streams | spurious |
| `antigravity.py:147` | streams | spurious |
| `gemini_otel.py:38` | `fh.read(_MAX_OTEL_BYTES)` | bound is *real*, rejection is not |

`gemini_otel` is the odd one and is fixed differently. Its read is already
bounded, so memory was never at risk — but rejecting the file *as well*
turned "read the first 25 MB" into "read nothing", which is strictly worse.
Only the rejection is removed; the bounded read stays and now reports when
it truncates.

## What

- **One shared reader.** `collectors.iter_bounded_lines` — symlink refusal,
  16 MiB per-line cap, 1 GiB total budget, truncation reported to the
  diagnostic log. `copilot`, `claude_code`, `antigravity` and `codex_app`
  all route through it, so the four cannot drift apart again. v5.32's local
  implementation in `codex_app` is now a delegation.
- **`gemini_otel`**: drop the size rejection from `_safe_path`; keep the
  bounded read; log when it truncates.
- **Guard against regression by source inspection.** A parametrised test
  asserts no collector contains `st_size >`. Crude, deliberately: the
  failure mode is a *silent early return*, so a re-added cap would look
  correct in every behavioural test — which is precisely how four copies
  survived.

Verified: `import-copilot --dry-run` goes from 2 sessions to **3**, and the
135.9 MB chat yields 47 lines where it previously yielded none.

## Out of scope

- **A doctor check for truncated or skipped transcripts.** v5.32 deferred it
  and this change does not add it. The diagnostic-log entry makes the loss
  discoverable, which is a real improvement over silence, but a first-class
  check is the better end state. Deferred rather than rushed: it should
  cover all collectors uniformly and there is no data yet on how often
  truncation actually fires.
- Re-importing the recovered Copilot history into the maintainer's ledger —
  that is a user action against their own data, not part of the fix.
- Attribution for imported sessions, which land `(unattributed)` because
  rollouts carry no git remote. A separate gap.
