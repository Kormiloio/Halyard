# v2.65 — Attribution Integrity & Visibility

## Problem (the moat half we under-protect)

Halyard's moat has two halves. **Cost-in-$** is rare; **project/client
attribution** is the genuinely irreplaceable one — it's what makes
Halyard about *billable client work and invoice evidence* rather than
usage vanity. A competitor can add cost tracking; "this AI session
provably maps to *this client project*" is the defensible asset.

This session shipped ~8 cost/data-integrity changesets. Attribution
got only *defensive* work (synthetic-row cleanup, active-timer tamper
guard, slug hardening). Nothing has improved attribution **accuracy,
confidence, or visibility**. Concretely, three gaps:

1. **No attribution confidence concept.** Cost carries trust labels
   (captured / calculated / allocated / inferred) surfaced everywhere.
   Attribution carries nothing equivalent. Worse, `attr_method`
   collapses the whole inference chain — `halyard.toml` walk-up, an
   explicit `repos.toml` git mapping, and the weak `git/<repo>`
   auto-slug — into a single `"git"`. A timer-attributed session and a
   guessed auto-slug session look identically trustworthy. For an
   *evidence* product that is a credibility hole.

2. **No attribution-quality canary.** `halyard doctor` shows the
   *current* unattributed count, but nothing detects **degradation**:
   adrift rate trending up, or a repo that used to attribute cleanly
   suddenly landing in `unattributed` (a moved project, `repos.toml`
   drift, a deleted `halyard.toml`). The v2.59 drift canary does
   exactly this for *model capture*; attribution has no equivalent, so
   silent attribution rot is invisible until a report looks wrong.

3. **Adrift value rots.** Every unattributed session is moat value
   lost. Doctor already groups them by remote and says "run halyard
   adopt", but doesn't emit the exact command per remote, so the
   friction-to-fix is just high enough that it doesn't get done.

## Goal

Bring attribution to cost-parity on trustworthiness — *record* the
real chain rung, *surface* it as a confidence label like cost trust,
*detect* attribution degradation, and *cut the friction* of fixing
adrift sessions. No silent writes; detection-only canary.

- **Record the chain rung.** Stop collapsing to `"git"`: capture
  whether attribution came from timer, `halyard.toml`, an explicit
  repo mapping, or the weak auto-slug. Additive; unavailable ⇒ today's
  value (back-compat, never fabricated).
- **Confidence label.** A derived `attribution_confidence` ordering
  (timer > mapped > toml > auto > none) surfaced per-session and as an
  aggregate mix in CLI / dashboard / MCP, mirroring the cost trust mix.
- **Attribution-quality canary** in `halyard doctor` (v2.59 pattern):
  `warning` when adrift rate regresses vs the prior window, or a
  previously-attributed remote starts landing unattributed.
- **One-command remediation.** Doctor emits the exact
  `halyard adopt` / `halyard link-repo` invocation per unaccounted
  remote (proposes; never writes).

## Constraints honored

- **No silent writes.** Remediation is *proposed commands*, not
  applied. The canary is read-only, on-demand (no daemon).
- **Unavailable is not zero / not fabricated.** A session whose chain
  rung can't be determined keeps today's behaviour; confidence is
  `unknown`, never guessed upward.
- **Back-compat.** Old log lines (no chain-rung token) parse and
  display exactly as now, bucketed as their best-known confidence.
- **Moat-additive.** Pure strengthening of the attribution pillar;
  nothing in the cost path changes.

## Non-goals

- Auto-adopting/auto-mapping repos (silent-writes violation).
- ML/heuristic project guessing beyond the existing deterministic
  chain.
- Multi-project-per-session splitting (a session is one work context;
  out of scope and likely wrong).

## Out of scope

Cross-tool attribution reconciliation and enterprise roll-up
attribution — those live in the gated enterprise layer.
