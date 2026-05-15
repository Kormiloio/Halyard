# Spec — TUI health visibility

## Requirement: Status bar flags failing health

WHEN the TUI renders its status bar AND any health check is `warning`
or `error`
THEN the status bar MUST show a compact indicator with the count of
failing checks and a hint of the key to open detail
AND WHEN all checks are healthy the status bar MUST NOT show the
indicator.

## Requirement: A keypress reveals health detail

WHEN the user presses the health key in the TUI
THEN a modal MUST open listing each failing check's label, status, and
detail, plus a line directing the user to run `halyard doctor` for full
diagnostics and fixes
AND WHEN no check is failing the modal MUST state all systems are
healthy
AND the modal MUST be dismissable (escape / the same key).

## Requirement: Reuse authoritative data, no new state

The health data MUST come from `reports.build_health_checks` (the same
source as the web dashboard). The feature MUST NOT add a new data file,
persisted state, or command, and MUST NOT auto-run fixes.

## Requirement: Injection-safe

Check-derived strings rendered in the modal MUST be escaped so a crafted
project/detail value cannot inject Textual markup (consistent with the
v2.38 TUI escaping invariant).
