# Spec: Integrity Verification for `~/.halyard/` State Files (Phase 1)

This change introduces an **opt-in** integrity verification layer for the
trusted state files under `~/.halyard/`. Phase 1 ships:

- A `state_integrity` module with read/write helpers and a `hash` mode.
- A single trust-boundary helper that the in-tree reads of `~/.halyard/active`,
  `~/.halyard/hub`, and `~/.halyard/projects` route through.
- `halyard doctor` surfaces the current mode.

Phase 2 (separate change): `hmac` mode with key management, shared-host
detection, and CLI tools to re-bless state.

## Requirement: A single `read_trusted_state(path)` helper MUST be the only
entry point for reading state files under `~/.halyard/`.

The helper MUST consult the current `state_integrity` mode and either
return the file's content verbatim (`mode == "off"`) or verify a sidecar
checksum before returning (`mode == "hash"`). A mismatch MUST raise
`IntegrityError`; the caller MUST be free to treat that as a fatal error
and refuse to continue with potentially-tampered state.

### Scenario: Default `off` mode preserves existing behaviour

WHEN `state_integrity` is unset (or explicitly `"off"`)
THEN `read_trusted_state(path)` returns `path.read_text(encoding="utf-8")`
AND no sidecar files are read or written
AND the function is a strict no-op overhead on the current code path.

### Scenario: `hash` mode verifies a sidecar checksum

WHEN `state_integrity = "hash"` in `halyard.toml`
AND `read_trusted_state(path)` is called for an existing file
THEN the helper computes `sha256(path.read_bytes())`
AND compares it against the contents of `path.with_suffix(path.suffix + ".sha256")`
AND raises `IntegrityError` if the sidecar is missing
AND raises `IntegrityError` if the sidecar's hex digest does not match.

### Scenario: `write_trusted_state(path, content)` keeps the sidecar in sync

WHEN any code writes content to a tracked state file via `write_trusted_state()`
THEN the file is written first with `encoding="utf-8"`
AND the `.sha256` sidecar is written with the new digest
AND both writes use the existing `locked_file` primitive so two processes
cannot interleave the data write with a stale sidecar.

### Scenario: A missing target file is not an integrity failure

WHEN `read_trusted_state(path)` is called and the target file does not exist
THEN the helper returns `None`
AND does NOT raise `IntegrityError`
AND does NOT consult the sidecar.

## Requirement: `read_active_project()` and `find_hub()` MUST go through the
trust-boundary helper.

These two functions are the highest-leverage attribution and routing
decisions in the codebase; they MUST NOT bypass `read_trusted_state()`.

### Scenario: Tampered active file fails closed in hash mode

WHEN `state_integrity = "hash"` and `~/.halyard/active` is edited out of band
WHEN `read_active_project()` is next called
THEN it raises `IntegrityError`
AND callers can choose to surface the error or fail closed.

### Scenario: Tampered hub pointer fails closed in hash mode

WHEN `state_integrity = "hash"` and `~/.halyard/hub` is edited out of band
WHEN `find_hub()` is next called
THEN it raises `IntegrityError`.

## Requirement: `halyard doctor` MUST report the active integrity mode.

### Scenario: Doctor surfaces mode

WHEN `halyard doctor` runs
THEN one of the OK/WARNING/SKIPPED rows is `Integrity` with the current
mode in its detail string
AND when mode is `"off"`, the row is `SKIPPED` (not a warning — opt-in
feature)
AND when mode is `"hash"`, the row is `OK` if all tracked sidecars
verify, otherwise `WARNING` with the path of the first mismatched file.

## Out of Scope (Phase 1)

- `hmac` mode with `~/.halyard/key`.
- Shared-host detection in doctor.
- Automatic migration of existing state files to add `.sha256` sidecars
  (today they have none; first `write_trusted_state()` call will create them).
- Wrapping per-collector state files (`gc-session`, `cc-session`,
  `cursor-session`) — these are ephemeral turn state, not durable
  attribution.
