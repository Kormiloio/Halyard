# v2.59 — Collector Schema-Drift Canary

## Problem

Halyard's collectors parse the *internal* formats of Claude Code,
Cursor, Gemini CLI, and Codex (hook payloads, JSONL transcripts). Those
formats are not contracts — an upstream release can rename or move the
model/usage fields. When that happens, capture does not crash: the
"unavailable is not zero" semantics and the evidence/implausibility
guards correctly refuse to *fabricate* data, so sessions still record
but with `model=<unknown>` / `0/0` tokens.

The failure is **silent degradation**: the ledger keeps filling, the
numbers quietly go blind, and the user only notices weeks later when a
report looks wrong. This is the same silent-trust failure class that
drove the v2.45–v2.56 data-correctness work — the difference is the
*source* is an upstream tool change, not an external writer.

Nothing today tells the user "a collector that used to capture model
data has stopped." `halyard doctor` reports hook *installation* and
unwired tools (v2.52) but not collector *output quality over time*.

## Goal

A **detection-only** canary in `halyard doctor` (and therefore the
dashboard/TUI health surfaces, which already render `DoctorReport`):
flag a tool whose recent captured sessions have regressed to
unreal-model output while its own history shows it used to capture a
real model.

- Per tool, compare a recent window against the tool's own baseline.
- Warn (never error — capture is not broken, enrichment degraded) with
  an actionable pointer (re-check the tool's hook / upstream version).
- Conservative thresholds: only fire on a *sustained* run, and only
  when the same tool has prior healthy sessions (so a brand-new or
  always-degraded tool doesn't false-positive).

## Constraints honored

- **Detection, not format-chasing.** The canary never tries to parse
  the upstream format; it watches Halyard's own output quality. No
  coupling to any tool's schema.
- **Read-only, on-demand, no daemon.** Runs inside
  `build_doctor_report()` only — same surface and stance as v2.52.
- **Low false-positive bar.** Model-degradation only (clear,
  defensible); requires a healthy baseline for that tool. Token-only
  drift is explicitly out of scope (legitimately ambiguous — e.g.
  Codex o-series reports `total_tokens` with `0/0` input/output).
- **No new data, no mutation.** Reads existing sessions; writes
  nothing.

## Non-goals

- Token-count drift detection (ambiguous; future, separate spec).
- Auto-remediation or auto-reinstalling hooks.
- Pinning/validating upstream tool versions.

## Out of scope

A general anomaly-detection framework over the ledger. This is one
narrow, high-signal canary, matching the v2.52 nudge pattern.
