# Integrity Verification for `~/.halyard/` State Files

## Summary

Add optional integrity verification — checksums or signed manifests — to the
trusted state files under `~/.halyard/`, so that tampering with a state file
cannot silently spoof project attribution, hub pointers, active timers, or
pricing/org configuration.

## Motivation

`ai_log.py`, `hub.py`, and the collectors trust the contents of
`~/.halyard/` without verification:

- `~/.halyard/active` — read by `read_active_project()` to attribute every
  new session.
- `~/.halyard/hub` — read by `find_hub()` to resolve where logs go.
- `~/.halyard/projects` — the cached project list used for assign-unattributed.
- `~/.halyard/cc-session` / `gc-session` / `cursor-session` — per-collector
  turn state with `cwd` and `session_id`.
- `~/.halyard/pricing-hash.txt`, `org-hash.txt` — already content hashes,
  but used as input not as a verified output.

For the **single-user local-only** product these are file-system trust
boundaries inherited from the user's account. That's appropriate for v0–v2.

But two scenarios start to matter:

1. **Shared / multi-tenant boxes** — dev VMs, CI runners, shared lab
   machines where multiple developers' processes can write to a
   sibling account's `~/.halyard/`.
2. **Enterprise rollout (v3+)** — the org-admin dashboard sources data
   from these files; an attacker who can drop a file (npm postinstall,
   compromised dotfile sync, malicious VSCode extension) can rewrite
   billable attribution without leaving an audit trail.

## Approach options

1. **HMAC manifest** — `~/.halyard/MANIFEST` lists each state file with an
   HMAC-SHA256 keyed by a secret in `~/.halyard/key` (mode 0600). Halyard
   refuses to read a file whose HMAC doesn't match.
2. **Content-addressed pointers** — `~/.halyard/hub` and similar pointer
   files carry an embedded checksum of the target; mismatches degrade to
   warning + reset.
3. **External attestation** — sign manifests with the user's GPG key.
   Highest assurance, highest setup cost.

Recommendation: option 1 for v3-aligned hardening, with option 2 as a
lighter intermediate step that catches accidental corruption without
adding key management.

## Scope

In:
- A `halyard.state.integrity` module that hashes/verifies state files.
- Wrap all `~/.halyard/*` reads behind a `read_trusted_state(path)`
  helper that fails closed on mismatch.
- Opt-in via `halyard.toml` (`state_integrity = "hmac"` | `"hash"` |
  `"off"`). Default `"off"` to preserve current behavior.
- `halyard doctor` warns if integrity is `"off"` on a shared host
  (detect via `getpwuid()` parent dir ownership ≠ effective uid).

Out:
- Encryption of state files. The threat is tampering, not disclosure.
- `ai-sessions.log` itself — append-only, already has per-line
  quarantine, and a separate change should propose Merkle-style chain
  integrity if needed.

## Acceptance

- With `state_integrity = "hmac"`: tampering with `~/.halyard/active`
  causes the next attribution read to fail closed with a clear error.
- With `state_integrity = "off"`: existing behavior, zero overhead, no
  new files on disk.
- `halyard doctor` reports current integrity mode and surfaces a
  warning when running on a shared host with integrity disabled.

## Risks

- **Key loss** — if `~/.halyard/key` is deleted, every state file looks
  tampered. Mitigation: doctor offers `halyard state reset --i-know`.
- **Backup compatibility** — users who sync `~/.halyard/` across
  machines must either sync the key or re-bless on each host. Document
  this.
