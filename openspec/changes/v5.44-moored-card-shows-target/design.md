# v5.44 — Design

## Why the count and not a nudge

The instinct was a doctor check: "this project is moored on the default
target, run `halyard voyage set`". That is the wrong shape for three
reasons.

1. **It fires on a correct state.** A project genuinely past its target
   is supposed to be moored. A warning would be advising the user to
   change a setting so that a true label stops being shown.
2. **Nothing downstream consumes the stage.** It is a cosmetic progress
   badge. Doctor exists for capture and attribution defects, where a
   wrong value costs billable minutes; spending a warning slot here
   devalues the ones that matter.
3. **The card already had the answer and withheld it.** Active cards
   render `2 / 20`. The moored branch renders creature, slug, stage,
   trait — everything except the two numbers that explain the badge.

Showing the count is smaller, needs no new copy, and resolves the
question at the point it is asked rather than in a different command.

## Placement

The count goes where the trait sits, not appended to the stage label.
`STAGE_LABELS["moored"]` is the string `"Shipshape · Moored"` — a single
value shared with the TUI and the CLI roster. Concatenating a count into
it would either leak per-card data into a shared constant or force the
label to be built differently on each surface.

The trait slot is free on every real card anyway: `creature_trait` is
only populated by `assign_creature` when a voyage completes to file, and
in the observed data every entry has `creature = ""` and
`creature_trait = ""` — the 🦭 on screen is the `v.creature or "🦭"`
fallback, not an earned creature. Where a trait *is* present it is kept
and the count is appended after it.

## Why not change `_DEFAULT_TARGET`

20 is arbitrary, and 107/20 is what triggered the question. But raising
it would silently re-stage every existing user's projects — a moored
badge becoming un-moored is a visible regression for anyone who had
legitimately finished a voyage. The default is not the defect; the
unexplained default is. One user's target is now 500, set explicitly,
which is the mechanism working as designed.
