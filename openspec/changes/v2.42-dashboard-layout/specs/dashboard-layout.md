# Spec — Customizable dashboard layout

## Requirement: Every panel is identifiable

WHEN the dashboard renders
THEN every grid panel and every top metric card MUST carry a unique,
content-stable `data-panel` attribute (never user-derived data).

## Requirement: Panels can be reordered by drag

WHEN the user drags a panel by its drag handle onto another element
with `data-panel` that shares the same parent container
THEN the panels reorder within that container
AND a drop whose target is in a different container is ignored
(metric cards and grid panels do not interleave).

## Requirement: Panels can be collapsed

WHEN the user activates a panel's collapse toggle
THEN the panel renders as header-only and the toggle indicates the
collapsed state; activating it again restores the panel.

## Requirement: Layout persists across reloads

WHEN the user has reordered and/or collapsed panels
THEN that order and collapsed set MUST be restored on the next page
load, including the dashboard's 10-second auto-refresh, via
`localStorage` (no server persistence).

WHEN a saved layout references an unknown id, OR a known panel has no
saved position
THEN the unknown id is ignored and the unsaved panel falls back to its
default position (forward-compatible with added/removed panels).

## Requirement: Reset to default

WHEN the user activates the layout reset control
THEN the saved order and collapsed set are cleared and the shipped
default layout is shown.

## Requirement: Fail safe

WHEN the layout script errors for any reason
THEN the server-rendered dashboard MUST remain fully visible (no blank
page); layout customization degrades, content does not.
