# Halyard Integration Contract

**Status — 2026-05-17:** Stable surface, additively versioned. This
document declares what external tools, downstream consumers, and the
additive Halyard-Enterprise layer may rely on.

## Why this exists

Halyard's durable value is a plain-text, locally-owned record of AI
work. For that to be a foundation others can build on (CI gates,
dashboards, finance/ROI tooling, the Halyard-Enterprise layer), the
*format* must be a contract, not an implementation detail. This is
that contract.

## The two surfaces you may build on

### 1. `ai-sessions.log` line grammar

Append-focused, UTF-8, one record per line. Two record types:

- **`s ` session record** — positional head
  (`s <start> <end> <tool> <model> <input_tok> <output_tok> <cost_usd>`)
  followed by space-delimited `key=value` tokens. Free-text values
  are percent-encoded so they cannot forge delimiters.
- **`a ` amendment record** — `a <session_hash> key=value …`, a
  correction keyed to the hash of an earlier `s ` line. The log is
  append-focused; corrections layer, they do not mutate.

Guarantees:

- **Additive only.** New optional `key=value` tokens may be
  introduced; the positional head and existing key semantics do not
  change meaning under you.
- **Old lines always parse.** A line written by an older Halyard is
  forever readable by a newer one.
- **Unknown tokens are preserved, not dropped** *(mechanism: v2.75,
  proposed — until it ships, unknown tokens are tolerated but not
  re-emitted; see that changeset)*. This is the **documented
  extension point**: a consumer (including Halyard-Enterprise) may
  add its own `key=value` tokens (e.g. `cost_center=`, `org_unit=`,
  `roi_ref=`) and Halyard will round-trip them without
  interpreting them. Do not overload reserved/known keys.

### 2. `--json` output schema (v2.69)

`report`, `usage`, `budget`, `status`, `evidence`, `health`,
`doctor` emit machine-readable JSON via the shared `jsonio` seam:
ISO datetimes, `Path`→str, `Decimal`→number, `_`-prefixed fields
omitted, errors as `{"error": …}` with non-zero exit. **Keys are
additive-only**; a documented key does not change type or meaning
under you. This is the contract for CI, scripts, and programmatic
consumers.

## What is NOT contractual

- The SQLite cache (`~/.halyard`) — a rebuildable read-model, schema
  may change freely; never read it directly, read the log or `--json`.
- Internal Python module layout, function signatures, TUI/dashboard
  HTML.
- Trust-label *wording* may refine; the *distinctions* (captured /
  calculated / allocated / inferred / mixed / unallocated) are
  stable.

## Attribution semantics

The attribution slug is `payer:work-unit` — an opaque
`namespace:unit` label for *whoever bears the cost*. Halyard OSS does
not interpret organizational hierarchy. A client you bill and an
internal cost center you measure ROI on are the same primitive with
different consumers; rollups/chargeback/ROI are an additive
Halyard-Enterprise layer over this contract, not a fork of it.

## Stability promise

Within the `0.x` line: additive changes only to the two surfaces
above; no silent semantic change to an existing token/key; unknown
tokens preserved (per v2.75). A breaking change to either surface
would be called out explicitly in the changelog and gated behind a
major version. Build on the log line and `--json`; treat everything
else as internal.
