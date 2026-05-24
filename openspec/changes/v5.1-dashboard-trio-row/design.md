# Design — v5.1 Dashboard trio row

## Layout change

The dashboard grid is a 12-column CSS grid (`.grid`, panels use `span-N`).
Three panels were re-spanned and reordered into one row at the Outcomes
position, in DOM order:

| Panel (`data-panel`) | Before | After |
|----------------------|--------|-------|
| `leverage` (Outcomes) | `span-12` | `span-4` |
| `wake` (Wake)         | `span-12` | `span-4` |
| `tools` (Capture)     | `span-4` (in Models cluster) | `span-4` (moved up) |

All `data-panel` ids are preserved and unique, so the drag-to-reorder /
collapse layout script (`halyard-layout-order-v1`) and
`tests/test_dashboard_layout.py` are unaffected.

## Leverage panel overflow fix

At `span-4` (~454px) the leverage panel overflowed horizontally by ~11px:

- `.leverage-grid` used `grid-template-columns: minmax(220px, 1fr) 2fr`. The
  rigid 220px minimum no longer fits a third-width panel. Changed to
  `minmax(0, 1fr) minmax(0, 1.4fr)` so both tracks can shrink below their
  content width.
- `.leverage-hint` (and its inline `<code>`) did not wrap. Added
  `overflow-wrap: anywhere` so the `halyard outcome sync` hint breaks instead
  of forcing a horizontal scrollbar.

The `<1100px` media query already collapses these panels to `span-12`, where
the original two-column proportions read fine; the relaxed track sizing is a
strict improvement there too.

## Verification

- DOM rects (desktop 1440px): trio share one row, equal 456px width, equal
  374px height, zero overflow; Models/Surface/Budget likewise align as a
  second three-up row.
- Wake heatmap cells render at 38×38px (was stretched far wider).
- Visual screenshot confirms balanced layout.
- ruff, ruff format, mypy clean; full suite 1483 passing.
