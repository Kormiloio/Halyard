# v2.43 — Actionable Health Warnings: Design

## Correction: no per-check fix data exists

Initial assumption was that the dashboard health carried `fix` text.
It does not — `reports.HealthCheck` is `label/status/detail` only;
`fix` lives on the unrelated `doctor.DoctorCheck` (CLI). So `_health_row`
is unchanged, nothing is fabricated, and the popup instead routes the
user to `halyard doctor` for authoritative diagnostics + fixes.

## Topbar pill → informative + clickable

The `<div class="status status-…">` becomes a `<button id="health-pill"
class="status status-…">` (keeps the same coloring classes). It always
carries a `title` summarizing state:

- healthy → `"All systems healthy"`
- otherwise → `"<n> check(s) need attention — click for detail"`

It is keyboard-focusable (a real `<button>`), so the tooltip and click
are accessible.

## The popup

`_health_popup(checks)` emits, always, a hidden container
`<div id="health-popup" hidden>`:

- a header ("System Health") + close button,
- one block per check that is not healthy: status dot, label,
  `detail`; plus a footer line pointing to `halyard doctor`,
- if nothing is wrong: a single "All systems healthy." line.

Content is server-rendered from `state.health` (same data the Health
panel uses) so there is no duplicated remediation logic and it works
without JS. All check-derived strings go through `_e()` (XSS-safe,
consistent with the rest of the dashboard and the v2.38 markup-escaping
work).

Positioning: fixed, anchored under the topbar (top-right), constrained
height with scroll. A backdrop class dims the page.

## Script

`_health_popup_script()` — a small fail-safe IIFE (try/catch, same
pattern as `_layout_script`): pill click toggles `hidden` + `open`
class; Escape and outside-click and the close button hide it. No
network, no storage. Wired next to the other scripts.

## CSS

`.status` made button-resettable (no default button chrome; inherit the
existing pill look). `#health-popup`, `.health-popup-card`,
`.health-popup-row`, `.health-fix`, backdrop.

## Tests

Python (`tests/test_dashboard_health_detail.py`):
- a warning/error check's detail appears in the popup container, and
  the popup includes the `halyard doctor` pointer,
- `#health-pill` is a `<button>` with a `title`,
- `#health-popup` container present,
- healthy project → popup says "All systems healthy", pill title
  reflects healthy.

Browser-verified: hover shows tooltip; click opens popup with the
failing check + fix; Esc / outside-click / close button dismiss; no
console errors.

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
