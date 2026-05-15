# Spec: v2.21 — Attribution Provenance

## Overview

An `attr_method=` KV field is added to the session log format to record how
each session's project attribution was determined. This makes the existing
`attribution_state` field on `OrgSession` live and provides an auditable trail
for financial attribution decisions.

---

## Timer attribution

### WHEN a session ends with attribution from the active timer (~/.halyard/active)
THEN the log line includes `attr_method=timer` and does NOT include the
`attribution:inferred` tag.

---

## Workspace root inference

### WHEN a session ends with attribution inferred from the workspace root (halyard.toml found walking up from CWD)
THEN the log line includes `attr_method=ws_root` and includes the
`attribution:inferred` tag.

---

## Git inference

### WHEN a session ends with attribution inferred from the git remote
THEN the log line includes `attr_method=git` and includes the
`attribution:inferred` tag.

---

## Backfill attribution

### WHEN assign_unattributed_sessions() attributes a previously unattributed session
THEN `attr_method=backfill` is written to the log line for that session.

### WHEN backfill_window() attributes a previously unattributed session
THEN `attr_method=backfill` is written to the log line for that session.

---

## Backward compatibility

### WHEN an old log line without attr_method= is parsed by from_log_line()
THEN `attr_method` is set to `None` on the resulting `AiSession`. No error is
raised and the line is not quarantined.

### WHEN an AiSession with attr_method=None is serialized by to_log_line()
THEN the attr_method= field is omitted from the output line (consistent with
the existing convention for None optional fields).

---

## Priority and mutual exclusivity

### WHEN both an active timer and a git inference are available at session end
THEN `attr_method=timer` is used. Timer attribution takes precedence over all
inference methods.

### WHEN workspace root inference and git inference are both available
THEN `attr_method=ws_root` is used. Workspace root takes precedence over git.
