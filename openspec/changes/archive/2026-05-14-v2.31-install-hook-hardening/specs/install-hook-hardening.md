# Spec: Install-Hook Hardening

## Cross-file duplicate detection

**Scenario 1: Local install skipped when global hook already exists**

GIVEN the hook is already present in `~/.claude/settings.json`
WHEN the user runs `halyard install-hook` (local, no --global flag)
THEN the hook is NOT written to `./.claude/settings.json`
AND the output tells the user the hook is already in `~/.claude/settings.json`

---

**Scenario 2: Global install skipped when local hook already exists**

GIVEN the hook is already present in `./.claude/settings.json`
WHEN the user runs `halyard install-hook --global-claude`
THEN the hook is NOT written to `~/.claude/settings.json`
AND the output tells the user the hook is already in `./.claude/settings.json`

---

**Scenario 3: Install proceeds when hook exists only in same-file**

GIVEN the hook is present in `./.claude/settings.json`
WHEN the user runs `halyard install-hook` again (same file)
THEN the existing within-file dedup fires and the hook is not duplicated
AND the output says "already present"

---

**Scenario 4: Install proceeds when neither file has the hook**

GIVEN neither `~/.claude/settings.json` nor `./.claude/settings.json` contains
the hook
WHEN the user runs `halyard install-hook`
THEN the hook is written to `./.claude/settings.json`
AND the output confirms installation

---

**Scenario 5: Other-file absent — no error**

GIVEN `~/.claude/settings.json` does not exist
WHEN the user runs `halyard install-hook` (local)
THEN the local install proceeds normally
AND no exception is raised for the missing global file

---

## Setup wizard scope

**Scenario 6: Multi-project answer installs globally**

GIVEN the user is running `halyard setup` interactively
WHEN the Claude Code hook step is reached
AND the user answers "y" to "Do you work on more than one project?"
THEN `_do_install_hook_claude(global_=True)` is called
AND the output confirms global installation

---

**Scenario 7: Single-project answer installs locally**

GIVEN the user is running `halyard setup` interactively
WHEN the Claude Code hook step is reached
AND the user answers "n" (or presses Enter) to the scope question
THEN `_do_install_hook_claude(global_=False)` is called
AND the output notes how to upgrade to global later

---

**Scenario 8: Non-interactive setup defaults to local**

GIVEN `sys.stdin` is not a TTY
WHEN `halyard setup` runs the Claude Code hook step
THEN the scope question is skipped
AND local install is used (existing behavior preserved)

---

## Doctor duplicate detection

**Scenario 9: Doctor warns when hook in both files**

GIVEN the hook command appears in both `~/.claude/settings.json` and
`./.claude/settings.json`
WHEN the user runs `halyard doctor`
THEN the output contains a WARN line about duplicate hooks
AND the output names both file paths
AND the output suggests removing hooks from one file

---

**Scenario 10: Doctor clean when hook in only one file**

GIVEN the hook appears in `~/.claude/settings.json` only
WHEN the user runs `halyard doctor`
THEN no duplicate-hook warning appears

---

**Scenario 11: Doctor clean when neither file has hooks**

GIVEN neither settings file exists or contains hooks
WHEN the user runs `halyard doctor`
THEN no duplicate-hook warning appears
AND no exception is raised
