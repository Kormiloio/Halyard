# Spec — Authenticated state integrity

## Requirement: HMAC mode

WHEN `state_integrity` is `"hmac"` (via `halyard.toml` or
`HALYARD_STATE_INTEGRITY`)
THEN each tracked state file MUST have a `.hmac` sidecar containing
`HMAC-SHA256(key, content)` hex, where `key` is 32 bytes from
`~/.halyard/integrity.key`
AND reads MUST verify with a constant-time comparison
AND a mismatch, a missing `.hmac` sidecar, or a missing/unreadable key
file MUST raise `IntegrityError` (fail closed — never downgrade to
"unverified").

## Requirement: Key file is protected

WHEN the integrity key is created
THEN it MUST be written with mode `0600` via an atomic
create+fsync+rename
AND the key bytes MUST NOT be written anywhere except that file (only
the HMAC digest is persisted in sidecars).

## Requirement: Modes do not cross-verify

WHEN switching between `hash` and `hmac`
THEN `hash` uses a `.sha256` sidecar and `hmac` uses a `.hmac` sidecar
SO THAT an unkeyed SHA-256 digest can never be accepted as an HMAC.

## Requirement: Honest security claims

The code docstring, `docs/trust-model.md`, and the PRD MUST state:
- `off`: no integrity.
- `hash`: detects corruption/accidental edits only; NOT tamper-resistant
  (an attacker who can write the file can rewrite its sidecar).
- `hmac`: detects tampering by any process that cannot read the 0600 key
  file; NOT a defense against an attacker who can read
  `~/.halyard/integrity.key` (full local-account compromise can forge).

No documentation may claim `hash` is tamper-resistant or that `hmac`
"resists local-account attacks".

## Requirement: Doctor guidance

WHEN `halyard doctor` reports integrity status
THEN it MUST show the active mode and, when mode is `hash`, note that
`hmac` is the tamper-resistant option.
