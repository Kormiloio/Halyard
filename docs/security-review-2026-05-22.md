# Halyard Security Review — 2026-05-22

**Reviewer:** Owner-led review pass, pre-OSS-release  
**Review Date:** 2026-05-22  
**Codebase Snapshot:** Halyard repository at the pre-v1.0 release-readiness checkpoint  
**Scope:** Targeted re-audit of state-integrity verification paths and the release-gate posture  
**Methodology:** Static read of state_integrity.py call sites + CI workflow inspection

> **Status: All findings in this review have been resolved.**
> See commit `59bcae4` (sidecar-downgrade defense) and commit
> `e64ba9c` (pip-audit gate). Resolution notes are inline below.

---

## Executive Summary

A focused follow-up to the 2026-05-08 Adrian/Kai review, motivated by
preparing the codebase for public open-source release. Three P1
findings surfaced, all in code that *looked* correct in isolation but
relied on a runtime mode being explicitly enabled to be safe — the
default runtime path was the unsafe one.

| ID    | Severity | Domain                 | Title                                                        | Status     |
|-------|----------|------------------------|--------------------------------------------------------------|------------|
| P1-1  | P1       | State Integrity        | `~/.halyard/active` sidecar downgrade on default-mode read   | Resolved   |
| P1-2  | P1       | State Integrity        | `~/.halyard/hub` sidecar downgrade on default-mode read      | Resolved   |
| P1-3  | P1       | Supply Chain / CI Gate | pip-audit failure masked by `\|\| true`, CVE present in lock | Resolved   |

A fourth P2 finding (manual reassignment provenance loss) is tracked
separately and resolved at commit `7daaf6f` — included here for
completeness only because it surfaced in the same pass.

| ID    | Severity | Domain        | Title                                                 | Status   |
|-------|----------|---------------|-------------------------------------------------------|----------|
| P2-1  | P2       | Trust Ledger  | Interactive reassignment did not record `attr_method` | Resolved |

---

## P1-1 — `~/.halyard/active` sidecar-downgrade defense was opt-in

**Severity:** P1  
**Affected:** `src/halyard/ai_log.py` `read_active_project()` (pre-commit `59bcae4`)  
**Resolved at:** commit `59bcae4`

### Finding

`read_active_project()` called
`state_integrity.read_trusted_state(active)` without detecting whether
an integrity sidecar existed on disk. `state_integrity.current_mode()`
defaults to `"off"` — in a default runtime (no project `halyard.toml`
with `state_integrity = "hash"|"hmac"`, no `HALYARD_STATE_INTEGRITY`
env override), a tampered `~/.halyard/active` would be silently
accepted *even if a stale `.sha256` or `.hmac` sidecar was present
alongside it*. The defense was opt-in; the attack surface was opt-out.

Impact: an attacker (or buggy process) able to write to
`~/.halyard/active` could redirect collector attribution to an
arbitrary project slug, corrupting downstream billing evidence and
invoice generation. This is the same threat model `reports.py:219`
already defended against for the per-project active-timer file using a
`detect_sidecar_mode()` check.

### Fix

Added `state_integrity.read_global_trusted_state(path)` as the
canonical entry point for any global (non-project-owned) trusted-state
file. The helper mirrors the per-project pattern in
`reports.read_active_timer`: if a sidecar exists on disk, its mode
wins over a default-off resolution. Migrated `read_active_project()`
to use it. Documented direct `read_trusted_state()` on a global
pointer as an anti-pattern.

Regression test:
`tests/test_state_integrity.py::test_read_active_project_blocks_downgrade`
proves the defense by writing the active file under hash mode (which
creates the sidecar), then clearing the env override and tampering the
file. The pre-fix code would have returned the tampered slug; the
post-fix code returns `None`.

### Risk after fix

The helper is itself a single-file surface and exercised by 5 new
tests. The defense still depends on the sidecar file existing — a
threat actor who deletes *both* the data file and the sidecar gets
the same default-off behavior as a fresh user. That's a fail-safe
degradation (no attribution, not wrong attribution) and matches the
documented threat model in `state_integrity.py`'s module docstring.

---

## P1-2 — `~/.halyard/hub` had the same downgrade weakness

**Severity:** P1  
**Affected:** `src/halyard/hub.py` `find_hub()` (pre-commit `59bcae4`)  
**Resolved at:** commit `59bcae4`

### Finding

Symmetric to P1-1. `find_hub()` read `~/.halyard/hub` through
`read_trusted_state(pointer)` with no sidecar detection. A tampered
hub pointer alongside a stale sidecar would be silently accepted under
default mode, redirecting hub-aware operations (cross-project session
search, invoice rollups) to an attacker-chosen directory.

### Fix

Migrated `find_hub()` to `read_global_trusted_state()`. Same shared
helper, same defense, same fail-closed behavior on tamper.

Regression test:
`tests/test_state_integrity.py::test_find_hub_blocks_downgrade`.

### Risk after fix

Same as P1-1.

---

## P1-3 — pip-audit CI step masked failures with `|| true`

**Severity:** P1  
**Affected:** `.github/workflows/ci.yml:41` (pre-commit `e64ba9c`)  
**Resolved at:** commit `e64ba9c`

### Finding

The CI release-gate had a pip-audit step that appended `|| true` to
the command, so any CVE in a pinned dependency produced a green step.
At review time `uv.lock` pinned `idna 3.13`, which has
**CVE-2026-45409** (fix: ≥3.15). The vulnerability was present in the
shipped lockfile; CI did not surface it.

This is a class of finding ("the gate exists but is no-op") that is
worse than no gate at all — reviewers and contributors see a green
checkmark and infer audit coverage that doesn't exist.

### Fix

Two changes in commit `e64ba9c`:

1. `uv lock --upgrade-package idna` → idna 3.13 → 3.16. Verified
   single-package upgrade with no transitive ripple.
2. Removed `|| true` from the pip-audit step in `ci.yml:41` so future
   CVEs in pinned dependencies fail the build.

`uv run pip-audit --skip-editable` now reports zero known
vulnerabilities; the gate will catch the next one.

### Risk after fix

pip-audit's coverage is bounded by its CVE database — a vulnerability
that exists but isn't in the database still ships. That's an intrinsic
limit of any audit tool, not a Halyard concern. The fix restores the
*intended* gate behavior.

---

## P2-1 — Interactive reassignment dropped attribution provenance

**Severity:** P2 (audit explainability, not a remote security hole)  
**Affected:** `src/halyard/orchestration.py:370` (pre-commit `7daaf6f`)  
**Resolved at:** commit `7daaf6f`

### Finding

`interactive_assign_unattributed()` moved an unattributed session
into a target project via `replace(session, project=target_project)`
without setting `attr_method`. Every other attribution path records
provenance (`timer`, `git`, `repo-map`, `backfill`, `manual` elsewhere
in `ai_log.py:928`), so manually-reassigned sessions were
indistinguishable in the audit ledger from high-confidence captures.

Impact is on invoice/audit explainability rather than confidentiality
or integrity: a billing dispute could not tell "user manually routed
this session" from "Halyard inferred this with high confidence."

### Fix

Set `attr_method="manual"` at the assignment site. Value already
existed in the enum (used by the confirm-amendment path), so no
schema change.

Regression test:
`tests/test_manual_sessions.py::test_assign_unattributed_records_manual_attr_method`.

---

## Process Notes

This review was conducted **after** an initial OSS-readiness audit
incorrectly reported the H-1/H-2 findings from the 2026-05-08 review
as still open. They had in fact been resolved (commit history shows
CSRF guard at `dashboard.py:168`, `_validate_base_url()` at
`log_agent.py:332`). The first-pass audit relied on reading the review
document verbatim rather than checking current source — a useful
reminder that security docs go stale and must be re-validated against
the codebase, not trusted as a standing source of truth.

The four findings in this document were caught only on a second,
deeper read driven by skepticism toward the first pass. The lesson is
recorded here so the next reviewer treats stale review docs as
hypotheses rather than facts.

---

## Sign-Off

**Review completed:** 2026-05-22  
**All findings:** Resolved in commits `59bcae4`, `e64ba9c`, `7daaf6f`  
**Test count delta:** +6 (1352 → 1358)  
**Next review recommended:** Before any change to `state_integrity.py`,
before re-enabling the pip-audit `|| true` (don't), and as part of the
standard pre-release gate from v1.1 onward.
