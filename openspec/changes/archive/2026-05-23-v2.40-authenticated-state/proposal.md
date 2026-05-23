# v2.40 — Authenticated State Integrity (HMAC)

## Problem

`state_integrity` "hash" mode stores `SHA-256(content)` in an **unkeyed**
`.sha256` sidecar next to the file. The independent security review rated
this **CRITICAL**: any process that can write `~/.halyard/active` can also
recompute and rewrite `active.sha256`, so the check detects accidental
corruption and naive single-file edits **but provides zero protection
against deliberate tampering** — exactly the threat the feature advertises.

Worse, the claims overstate the guarantee:

- `state_integrity.py` docstring: *"Phase 2 will add an `hmac` mode … that
  resists local-account attacks"* — and the existing prose implies "hash"
  already gives tamper detection.
- The archived design always specified an HMAC mode; it was never built.

So there are two problems: a missing authenticated mode, and documentation
that overclaims what ships today.

## Goals

1. Add `state_integrity = "hmac"`: keyed HMAC-SHA256 sidecars using a
   per-user secret at `~/.halyard/integrity.key` (mode 0600).
2. Make the security claims **precise and honest**, in code docstrings,
   `docs/trust-model.md`, and the PRD:
   - `off` — no integrity.
   - `hash` — corruption/accident detection **only**; explicitly *not*
     tamper-resistant (attacker who writes the file rewrites the sidecar).
   - `hmac` — detects tampering by any process that **cannot read the
     0600 key file**. It is **not** a defense against a full local-account
     compromise (an attacker who can read `~/.halyard/integrity.key` can
     forge a valid sidecar). State the boundary plainly; do not imply
     more.
3. `halyard doctor` reports the mode and recommends `hmac` over `hash`.

## Non-goals

- Encryption of state files (threat is tampering, not disclosure).
- A signed remote manifest or asymmetric keys.
- A dedicated `halyard state reset` command (recovery path is documented;
  a CLI affordance is a possible follow-up).

## Out of scope

The `hash` mode is retained for zero-dependency corruption detection but
documented as non-adversarial. No change to which files are tracked or to
the `halyard.toml` key name.
