# v5.1 — Dashboard: group Outcomes · Wake · Capture into one row

## Why

On the Bridge dashboard, three panels each occupied more horizontal space
than their content needed:

- **Outcomes** ("Did it ship?") rendered full-width (`span-12`) for a compact
  headline-plus-five-rows stat block.
- **Wake** (the monthly activity heatmap) rendered full-width, stretching its
  7 day-columns to ~180px cells — sparse and hard to read as a calendar.
- **Capture** ("Tools") was already `span-4` but lived down in the
  Models/Budget cluster, away from the other two.

The result was wasted width and extra vertical scrolling.

## What changes

Place Outcomes, Wake, and Capture on a single three-up row (`span-4` each)
at the Outcomes position. No data, endpoints, or panel identities change —
this is a presentational reflow only.

Side effect: pulling Capture out of the Models cluster leaves
**Models · Surface · Budget** as its own clean three-up row.

## Impact

- Affected: `src/halyard/dashboard.py` (panel order + span classes, leverage
  panel CSS).
- No change to stored data, the ai-sessions.log format, or any CLI command.
- Responsive behavior unchanged: below 1100px all panels still collapse to
  full-width stacked.
