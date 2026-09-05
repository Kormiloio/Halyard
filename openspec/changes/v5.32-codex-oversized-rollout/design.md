# v5.32 — Design

## Why the cap was the wrong bound, not just the wrong number

The obvious fix is "raise 25 MB to something bigger". That would have
unblocked this machine and left the defect intact: whatever the number, a
whole-file cap on a streaming reader still means every session above it
silently disappears, and rollouts grow without limit.

The mismatch is that `_iter_jsonl_lines` never loaded the file. It is a
generator doing `yield from fh`, so peak memory is the longest line. A
whole-file limit therefore constrained nothing about resource use — it only
set the size at which a session became permanently uncapturable. The bound
that matches the read is per line, which is precisely what
`gemini_history` settled on (`_MAX_ROLLOUT_LINE_BYTES`) after hitting an
825 MB rollout.

Keeping a total budget as well is deliberate: streaming bounds memory, not
time, and a genuinely hostile file could stream forever. 1 GiB is chosen to
sit above observed real rollouts (813 MB here, 825 MB in the Gemini case)
rather than below them, which is the mistake being corrected.

## Skip-and-continue versus abandon

The two bounds behave differently on purpose:

- **Over the per-line cap** → skip that line, keep reading. One corrupt or
  pathological line should cost one line, not the whole session. This
  matches `gemini_history`, which comments the same intent.
- **Over the total budget** → stop reading and keep what was parsed so far.
  The session is still recorded, just truncated, which is strictly better
  than the previous all-or-nothing behaviour.

Both are now observable, which the old code was not.

## Why truncation is logged rather than raised

An importer that raises on a large file is an importer that aborts a batch,
and v5.16/B08 already established the opposite contract here: one bad
rollout must skip-and-continue, never take down every later session. So
truncation goes to the diagnostic log via `_log_error`, the same channel the
hub client uses for degraded-but-continuing conditions.

`_log_error` takes an exception, so a `RuntimeError` is constructed purely
as the carrier for the message. Slightly awkward, but it keeps this on the
established logging path instead of inventing a second one for a single call
site.

## What "verified" means here

The interesting assertions are about a 813 MB file that cannot be committed
to the repo, so the tests use synthetic fixtures for the *bounds* and the
real file was used once, manually, to confirm the end-to-end claim:

| check | before | after |
|---|---|---|
| lines yielded from the 813 MB rollout | 0 | 13,338 |
| `_parse_session_file` | `None` | parses |
| `import-codex` | "No new Codex sessions" | imports 2 |
| recorded Codex total | 148,225,877 | 419,845,235 |
| drift canary | firing | silent |

The unit tests cover the bounds themselves — a file over the old 25 MB cap
now reads, an over-long line is skipped without killing the session, the
total budget truncates *and* logs, symlinks are still refused — because
those are the behaviours a future change could regress. The 813 MB figure is
evidence for the proposal, not something a test suite should try to
reproduce.

## The number that changed

One session's recorded total moved from 103,842,457 to 371,138,080. That is
not a re-count of the same data; the earlier figure was parsed from a
19.7 MB snapshot of a rollout that is now 852 MB, and everything after the
snapshot had been dropped on the floor. Any analysis built on the old
ledger — spend, peak usage, model mix — was reasoning from roughly a
quarter of the Codex data.
