# v2.48 — Dashboard Data Correctness

## Problem

The product is its data; right now the default dashboard is wrong:

1. **`halyard dashboard` defaults to the hub.** The hub log
   (`…/artifacts/ai-sessions.log`) is an unattributed/junk dump (344
   `claude-unknown 0/0 $0` stubs + recurring synthetic Cursor/Gemini
   placeholders). The user's real work (443 sessions, ~$2k) lives in
   the **project** log and is never shown. Every panel — sessions,
   cost, ranks, usage, outcomes, wake calendar — is computed off the
   wrong file.

2. **Registry pollution from tests.** `~/.halyard/projects` contains
   hundreds of `…/pytest-of-…/test_init_*` temp paths: the test
   suite's `halyard init` writes to the real registry. (Mitigated at
   read time by `read_registry()` skipping nonexistent dirs, but the
   file grows unboundedly and it is a real isolation defect.)

3. **Synthetic implausible sessions.** Cursor `2000/400` and Gemini
   `100/50` rows keep being written with a frozen
   `start=2026-05-07T10:00:00` (multi-day "sessions"). They carry
   nonzero tokens + a real model, so the v2.46/47 evidence guard
   correctly does not catch them — but a many-hours/days hook session
   is detectable as broken.

## Goals

1. **Aggregate by default.** `halyard dashboard` with no
   `--project-dir` shows the union of all *real* registered project
   logs (registry ∩ existing, plus the hub for genuinely unattributed
   work), deduped — total real work, not a junk hub. `--project-dir`
   still scopes to one project.
2. **Implausible-session guard.** Collectors reject a hook session
   whose duration exceeds a sane bound (the synthetic frozen-start
   rows), shared across collectors.
3. **Registry isolation.** The test suite must not write to the real
   `~/.halyard/projects`; add a guard and an autouse fixture. One-time
   prune of the polluted entries (operational, with backup).
4. **Re-clean the logs.** Backup + predicate-prune the hub's 344 stubs
   and any residue so the data behind the now-correct view is clean.

## Non-goals

- Re-architecting per-project sub-reports (timeclock, plans, budget)
  into cross-project aggregates — those stay scoped to the resolved
  primary dir; the *session-derived* panels (the user-visible
  correctness issue) aggregate.
- Distinguishing synthetic-but-plausible payloads (Halyard can't).

## Out of scope

The external driver feeding synthetic Cursor/Gemini payloads is not
Halyard code; the implausible-duration guard is the in-product defense.
