# Spec — Cursor/Gemini hook install de-dup

## Requirement: Idempotent across install paths

WHEN `install-cursor-hook` or `install-gemini-hook` runs AND the target
config already contains a halyard hook for an event — regardless of the
absolute halyard path in that command
THEN the installer MUST NOT add a second halyard hook for that event;
the result MUST contain exactly one halyard hook per event, pointing at
the currently-resolved halyard binary.

## Requirement: Stale halyard entries are healed

WHEN the existing config contains a halyard hook whose path no longer
exists or differs from the current binary
THEN install MUST replace it (remove the stale one, add the current
one), not leave both.

## Requirement: Foreign hooks preserved

WHEN the config contains non-halyard hooks (other tools/vendors)
THEN install MUST preserve them and their relative order; only halyard
entries are rewritten.

## Requirement: True no-op when unchanged

WHEN install runs and the only halyard hook already points at the
current binary
THEN the file MUST be left byte-unchanged and the command MUST report
"already present".

## Requirement: A command is "halyard" iff arg0 basename is halyard

Detection MUST key off the basename of the command's first token
(`halyard` / `halyard.exe`), never the full path, and MUST NOT
misclassify another vendor's command as halyard.
