# v2.42 — Customizable Dashboard Layout

## Problem

The web dashboard ("The Bridge") renders a fixed stack of ~15 panels
(plus the top metrics row) in a hard-coded order. Different users care
about different things — a freelancer watching budget vs. someone
tuning model mix — but everyone gets the same long scroll with no way
to prioritize or hide what they don't use.

## Goals

- Let the user **reorder** panels by dragging them (within their
  container: metric cards among metrics, grid panels among grid panels).
- Let the user **collapse/minimize** any panel or metric to just its
  header, and expand it again.
- **Remember** the chosen order and collapsed set across reloads
  (including the dashboard's own 10-second auto-refresh).
- A **reset** control returns to the shipped default layout.

## Approach

Client-side only, persisted in `localStorage`. The page is
server-rendered and auto-refreshes every 10s; the layout script
re-applies the saved layout on every load. This:

- adds **zero server surface** — no new endpoint, no request handling,
  no state in `~/.halyard`. This is deliberate: the dashboard's request
  path was just hardened across v2.38–v2.41 and a single-user local tool
  does not need server-persisted UI prefs.
- reuses the existing inline-script + `localStorage` convention already
  used for the theme toggle (`halyard-theme`).

Tradeoff (accepted): the layout is per-browser/per-machine and not
synced. For a local single-user dashboard this is the right call;
cross-browser sync is explicitly out of scope.

## Non-goals

- Server-persisted or multi-device-synced layouts.
- Resizing panels or changing their grid spans.
- Cross-container drag (a metric card into the 12-col panel grid) —
  this would break grid spans; drag is constrained to siblings.

## Out of scope

Theming, panel content, and the auto-refresh interval are unchanged.
