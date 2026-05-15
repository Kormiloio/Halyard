# v2.39 — Input Injection Hardening

## Problem

An independent full security review (cross-checked against a Copilot
review) found concrete attacker-controlled-input → injection / DoS chains
that the posture-level review missed. Four are in scope here; they share a
root cause: untrusted external input (a cloned repo's git config, a hook
payload, a tool-written history file, a commit diff) is consumed without
validation.

1. **HIGH — TOML injection via `git config user.name`.** `halyard init`
   interpolates `_detect_business_name()` (raw `git config user.name`)
   into `halyard.toml` with `str.format` and no escaping. A cloned repo's
   *local* `.git/config` overrides the global, so a malicious repo can
   set `user.name` to a value that breaks out of the quoted TOML string
   and injects arbitrary keys into the trust-relevant config the victim
   then runs `halyard init` against.

2. **HIGH — `transcript_path` traversal / resource exhaustion.** The
   Claude Code Stop-hook payload is untrusted; `transcript_path` is fed
   straight to `Path(...).read_text()` (whole file) with no validation.
   A hostile process piping a crafted payload to `halyard cc-hook` (or a
   malicious MCP) can point it at an arbitrary file, a multi-GB file, or
   a FIFO/device.

3. **MEDIUM — Unbounded `read_text()` of Gemini history.** Any local
   process can drop a multi-GB `~/.gemini/tmp/.../session-*.json`;
   `gemini_history` reads the whole file into memory, OOM-killing the
   importer/hook. (Codex was already streamed in v2.38; Gemini was not.)

4. **LOW — `config_history` audit aborts on a crafted commit diff.** A
   `+rate = 1.2.3` line makes `float()` raise an uncaught `ValueError`,
   killing the rate-history audit.

## Goals

- No untrusted string reaches a TOML/log/path sink without validation or
  safe serialization.
- External files are size-bounded and, where untrusted, path-validated
  before being read.
- A malformed commit diff degrades gracefully, never aborting the audit.

## Non-goals

- The state-integrity authenticity gap (HMAC) — tracked separately as
  `v2.40-authenticated-state`; it is a design change, not input
  validation.
- Pricing redirect-pinning, `_halyard_exe` argv trust, dashboard
  constant-time compare, and the trust-model docs — smaller items
  batched elsewhere.

## Out of scope

No change to the `halyard.toml`, hook-payload, or log line formats. This
is validation/serialization hardening only.
