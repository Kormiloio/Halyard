# v2.36 — Proof Score Transparency

## Problem

The current proof score is a single number with a label like "gaps present."
Two things make it confusing:

1. **The formula is hidden.** Score = (attribution rate × 60%) + (token capture
   rate × 40%). A user with zero attribution but full token capture sees 40%,
   which is technically correct but looks like a bug. With 74 sessions all
   adrift, the expected score is 0% — but Halyard shows 40% because tokens were
   captured. This erodes trust.

2. **"Gaps present" doesn't tell the user what to fix.** A low score could mean
   sessions are unattributed, tokens weren't captured, or both. The current
   display gives no direction.

## Proposed changes

### Split the single score into two visible components

Instead of one "Proof Score — 40%" display, show:

```
Proof Score
  Attribution   0%   ● 74 sessions unattributed
  Token capture 100% ● all sessions have token counts
  ─────────────────────────────────────────────
  Combined      40%  gaps present
```

The combined score remains the same formula. The two components are shown
separately so the user knows exactly which gap to close.

### Actionable fix prompts

Each failing component shows a one-line fix:

- Attribution < 100%: "Run `halyard assign-unattributed` to attribute 74 sessions"
- Token capture < 100%: "N sessions recorded without token counts — check hook setup"

### Voyage panel

The Current Voyage panel already shows the proof score. Update it to show
the component bars inline (compact, two rows):

```
PROOF SCORE
[░░░░░░░░░░░░░░░░░░░░]  0%  attribution
[████████████████████] 100%  tokens
                        40%  combined
```

### Health panel

The Attribution health check currently shows "74 session(s) adrift" as a
warning. Keep that, but also surface token capture rate as a separate check
so both gaps are visible in the health list.

### What stays the same

- The proof score formula does not change.
- The 80% / 60% thresholds for healthy / warn / low do not change.
- Session records are not modified.

## Success criteria

- A user with 74 adrift sessions immediately understands the 40% score (token
  capture is 100%, attribution is 0%).
- The fix action is shown next to the failing component.
- The combined score still displays for at-a-glance reference.
- No new data formats or commands.
