# v2.40 — Authenticated State Integrity: Design

## Mode resolution

`IntegrityMode` becomes `Literal["off", "hash", "hmac"]`. Both
`_read_mode_from_toml` and the `HALYARD_STATE_INTEGRITY` env check accept
`"hmac"`. Default stays `"off"`; resolution order and the per-project
`_MODE_CACHE` are unchanged.

## Key management

`~/.halyard/integrity.key` holds 32 random bytes, hex-encoded, file mode
`0600`, written with the existing `_atomic_write` (which already creates
with `0o600` + fsync + rename).

`_integrity_key(*, create: bool) -> bytes`:
- read path (`create=False`): if the key file is missing or unreadable,
  raise `IntegrityError` — we must fail closed, never silently downgrade
  to "no verification".
- write path (`create=True`): generate via `secrets.token_bytes(32)` and
  atomically create it if absent; reuse if present.

The key never leaves the process; only the hex HMAC digest is written to
the sidecar.

## Sidecars

`hash` keeps the `.sha256` suffix. `hmac` uses a distinct `.hmac` suffix
so the two modes can never cross-verify (a `.sha256` written under `hash`
must not be mistaken for an HMAC). `_sidecar(path, mode)` selects the
suffix.

## Read / write

`read_trusted_state`:
- `hmac`: require the `.hmac` sidecar; compute
  `hmac.new(key, content, sha256).hexdigest()`; compare with
  `hmac.compare_digest` (constant-time); mismatch or missing sidecar →
  `IntegrityError`.

`write_trusted_state`:
- `hmac`: ensure the key exists (`create=True`), compute the HMAC,
  `_atomic_write` the `.hmac` sidecar **before** the data file (same
  crash-safety ordering already used for `hash`).

## Honest claims (the other half of this change)

Rewrite the `state_integrity.py` module docstring, `docs/trust-model.md`,
and the PRD integrity section to state the three-tier guarantee exactly
as in proposal.md — in particular: **`hash` is corruption detection, not
tamper resistance**, and **`hmac` raises the bar to "an attacker who
cannot read the 0600 key", not "tamper-proof"**. Delete the existing
"resists local-account attacks" wording; that is false for any attacker
who can read the user's own home.

## Recovery / migration

Switching `off`/`hash` → `hmac` leaves existing data files without a
`.hmac` sidecar. Reads then raise `IntegrityError`; the two callers
(`read_active_project`, `find_hub`) already catch it and return `None`
(graceful degradation), and the next `write_trusted_state` regenerates
key + sidecar. Deleting `integrity.key` behaves the same way. This is
acceptable, fail-closed behavior; it is documented in `trust-model.md`
rather than given a bespoke CLI command (noted as a possible follow-up).

## Tests

`tests/test_v240_authenticated_state.py`:
- round-trip: write then read under `hmac` verifies.
- tamper the data file only → `IntegrityError`.
- tamper data **and** recompute a plain SHA-256 sidecar → still
  `IntegrityError` (proves the key matters; this is the exact attack that
  defeats `hash`).
- forge with the real key → verifies (confirms the boundary: key holder
  can forge — documents the honest limitation).
- missing key on read → `IntegrityError` (fail closed).
- key file is mode `0600`.
- `hash` mode unchanged (regression).

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
