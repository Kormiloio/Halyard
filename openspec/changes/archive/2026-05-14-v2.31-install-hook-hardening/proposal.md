# Proposal: v2.31 — Install-Hook Hardening

## Why this change

`halyard install-hook` has a duplicate-fire bug that inflates session counts
for any user who runs both a local and a global hook install. The two installs
are the natural path for a multi-project user: local install first (during
`halyard setup` in their first project), global install later (when they start
a second project and realize they need coverage everywhere).

The duplicate is silent. The user sees no error, no warning, and no indication
that every Claude Code session is being recorded twice. The only observable
symptom is an inflated session count in `halyard report`.

This was discovered on 2026-05-14 when investigating why sessions from one
project were not appearing in another. The root cause: hooks were installed in
both `~/.claude/settings.json` (global) and `./.claude/settings.json` (local
project). The existing dedup check in `_do_install_hook_claude()` only reads
within one file at a time, so it cannot detect that the same hook is already
present in the other file.

---

## Two problems, one changeset

### Problem 1 — Cross-file duplicate detection gap

`_do_install_hook_claude(global_=True)` checks `~/.claude/settings.json` for
existing hook entries before adding. `_do_install_hook_claude(global_=False)`
checks `./.claude/settings.json`. Neither checks the other file.

A user who runs `halyard install-hook` (local) then `halyard install-hook
--global-claude` (global) ends up with two identical hooks firing on every
Claude Code event. Session records are doubled. Costs, token counts, and
session totals are wrong.

**Fix:** Before writing a new hook entry, check both files. If the hook command
is already present in either the local or the global settings file, skip the
write and tell the user where the existing hook lives.

### Problem 2 — Setup wizard does not explain hook scope

`halyard setup` defaults to a local hook install (`global_=False`). It does
not explain that a local hook only captures sessions when Claude Code is invoked
from within that specific project directory, and it does not ask whether the
user works across multiple projects.

A user who wants multi-project coverage must discover `--global-claude`
independently. If they later find it and run it without knowing the dedup risk,
they hit Problem 1.

**Fix:** During `halyard setup`, after the user selects Claude Code as a tool,
ask one question: "Do you work on multiple projects?" If yes, install globally.
If no (or unsure), install locally with a note that they can switch later with
`halyard install-hook --global-claude`.

---

## What this change does not do

- Does not change the hook commands themselves or what they capture.
- Does not automatically repair existing duplicate entries in settings files.
  The user is responsible for cleaning up past duplicates; `halyard doctor`
  will flag them (see success criteria).
- Does not change Gemini or Cursor hook install paths — they are single-target
  by design and do not have this problem.

---

## Files changed

| File | Change |
|---|---|
| `src/halyard/cli.py` | Cross-file dedup in `_do_install_hook_claude()`; setup wizard scope question |
| `tests/test_install_hook.py` | New tests for cross-file dedup and scope warning |

---

## Success criteria

1. Running `halyard install-hook` (local) when the hook is already in
   `~/.claude/settings.json` prints a warning and skips the write.
2. Running `halyard install-hook --global-claude` when the hook is already in
   `./.claude/settings.json` prints a warning and skips the write.
3. `halyard setup` asks about multi-project usage and installs globally when
   the user answers yes.
4. `halyard doctor` detects hooks present in both local and global settings and
   reports them as a warning with a remediation instruction.
5. All existing tests pass; ≥ 6 new tests added.
