# Spec — Actionable health warnings

## Requirement: Status pill is informative and accessible

WHEN the dashboard renders the topbar status pill
THEN it MUST be a focusable control with a `title` that, on hover,
summarizes health: "All systems healthy" when healthy, otherwise a
count of checks needing attention.

## Requirement: Clicking the pill reveals detail

WHEN the user activates the status pill
THEN a popup MUST appear listing every non-healthy check with its
status and detail, sourced from the same health data as the Health
panel, plus a line directing the user to run `halyard doctor` for full
diagnostics and fixes
AND it MUST be dismissable by a close control, the Escape key, and an
outside click.

WHEN no check is failing
THEN the popup states that all systems are healthy.

## Requirement: Display only, fail-safe

The popup content MUST be server-rendered (works without JS) and all
check-derived text MUST be HTML-escaped. The toggle script MUST be
wrapped so any failure leaves the dashboard fully usable, and it MUST
NOT introduce any server endpoint, stored state, or auto-remediation.
