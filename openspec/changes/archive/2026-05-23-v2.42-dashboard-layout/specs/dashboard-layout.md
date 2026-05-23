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

## Requirement: Controls sit in the top-right of every box

WHEN the drag/collapse controls are injected
THEN they MUST appear in the top-right corner of the box for both grid
panels and metric cards (metric cards, which have no panel header, pin
the controls to the card's top-right corner).

## Requirement: Panels can be collapsed

WHEN the user activates a panel's collapse toggle
THEN the panel renders as header-only and the toggle indicates the
collapsed state; activating it again restores the panel.

## Requirement: Universal collapse/expand-all

WHEN the user activates the top-of-page "collapse all / expand all"
control
THEN every layout box collapses if any is currently expanded, otherwise
every box expands
AND the collapsed set is persisted like individual toggles
AND the control's label reflects the next action and stays in sync when
individual panels are toggled.

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
