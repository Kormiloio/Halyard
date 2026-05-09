# Spec: Attestable AI Work Appendix Format

## Purpose

Halyard's appendix is a portable, signed, verifiable artifact that
documents AI-assisted work for a client / period / project. This spec
defines the wire format. Other tools may emit and verify appendices
that conform to this spec.

## File extension

`.appendix.json` for the canonical artifact.
`.appendix.pdf` for the human-readable PDF wrapper (which embeds the
JSON in metadata).

## Required fields

| Field                                  | Type      | Notes                                                |
|----------------------------------------|-----------|------------------------------------------------------|
| `halyard_version`                      | string    | Semver of issuing tool                              |
| `appendix_version`                     | int       | Schema version, currently `1`                       |
| `appendix_id`                          | string    | `appx_YYYY-MM-DD_<8hex>`; unique per issuer         |
| `issued_at`                            | ISO 8601  | UTC                                                 |
| `issuer.name`                          | string    | Free-form                                           |
| `issuer.email`                         | string    | Free-form                                           |
| `issuer.public_key_fingerprint`        | string    | `sha256:<hex>` of the Ed25519 public key            |
| `recipient.name`                       | string    | Free-form                                           |
| `recipient.email`                      | string    | Free-form                                           |
| `scope.client_slug`                    | string    | Halyard client identifier                           |
| `scope.period_start`                   | ISO date  |                                                     |
| `scope.period_end`                     | ISO date  |                                                     |
| `summary.total_human_hours`            | float     | From `time.timeclock` for the period                |
| `summary.total_ai_sessions`            | int       | Count of sessions in scope                          |
| `summary.total_ai_cost_usd`            | float     |                                                     |
| `summary.tools_used`                   | string[]  | Distinct tool names                                 |
| `summary.trust_label`                  | enum      | Worst label across sessions                         |
| `sessions[]`                           | array     | Session detail                                      |
| `signature.algorithm`                  | string    | `Ed25519` for v1                                    |
| `signature.value`                      | base64    |                                                     |
| `signature.signed_fields`              | string[]  | List of top-level fields covered                    |

## Optional fields

| Field                                  | Type      | Notes                                                |
|----------------------------------------|-----------|------------------------------------------------------|
| `scope.project_slug`                   | string    | Narrow scope to one project within a client         |
| `pubkey_url`                           | URL       | Where verifiers can fetch the issuer's public key   |
| `notes`                                | string    | Free-form, no length limit                          |

## Session detail (`sessions[]` element)

| Field                                  | Type      | Notes                                                |
|----------------------------------------|-----------|------------------------------------------------------|
| `session_hash`                         | string    | First 12 hex chars of sha256 of the original `s` line|
| `started_at`                           | ISO 8601  |                                                     |
| `ended_at`                             | ISO 8601  |                                                     |
| `tool`                                 | string    |                                                     |
| `model`                                | string    |                                                     |
| `cost_usd`                             | float     |                                                     |
| `trust_label`                          | enum      | Per-session trust label                             |
| `file_paths_hashed[]`                  | string[]  | `sha256:<hex>` per touched file (if collector got them) |
| `tool_calls`                           | int       | Optional                                            |
| `tool_errors`                          | int       | Optional                                            |
| `code_added`                           | int       | Optional                                            |
| `code_removed`                         | int       | Optional                                            |

## Forbidden content

The following must never appear in any field:

- Prompt text or any user input to the AI tool.
- Source code or file content.
- Unhashed file paths.
- API keys, tokens, environment variables.
- Diff content.

A conformant emitter must include automated checks that reject documents
violating these constraints.

## Canonicalization

The document is canonicalized via RFC 8785 (JCS) before signing:

1. Object keys sorted lexicographically.
2. Whitespace removed.
3. Numbers in shortest exact form.
4. UTF-8 encoded.

The `signature` object is removed before canonicalization. Its presence
in the final output does not affect the canonical bytes.

## Signature algorithm (v1)

Ed25519 over the JCS-canonical bytes, base64-encoded for transport.

Future versions may add other algorithms; readers must check
`signature.algorithm` and fall back to "unknown algorithm" failure if
unsupported.

## Verification protocol

1. Parse JSON.
2. Extract `signature`; remember its `value`.
3. Remove `signature` field from the document.
4. Apply JCS canonicalization to the remaining document.
5. Look up the issuer's public key by `issuer.public_key_fingerprint`:
   a. Try `~/.halyard/keys/known/<fingerprint>.pub` if running locally.
   b. Try `pubkey_url` if present in the document.
   c. Try `halyard.dev/keys/<fingerprint>`.
   d. If none found, prompt the user.
6. Verify the signature against the canonical bytes.
7. Return Pass/Fail.

## Replay protection

Recipients must record `appendix_id` values they have seen. A second
appendix with the same `id` is a replay attempt or an issuer mistake;
recipients should reject it.

## Versioning

The `appendix_version` field gates schema evolution. v1 is the format
specified here. Future versions:

- v2 (planned): adds outcome-graph fields (PR refs, commit counts, test
  results) — additive, backward-compatible.
- v3+ (TBD): may add new signature algorithms or revocation pointers.

A v2 verifier reading a v1 document must succeed (additive fields are
absent). A v1 verifier reading a v2 document should warn "newer
version, ignoring unknown fields" but still verify the signature on the
JCS form.

## Conformance test fixtures

This spec ships with a set of test fixtures at
`docs/appendix-fixtures/`:

- `valid-minimal.appendix.json` — smallest valid v1 appendix.
- `valid-full.appendix.json` — all optional fields populated.
- `invalid-missing-required.appendix.json` — missing required field.
- `invalid-tampered-summary.appendix.json` — body modified, signature
  intact.
- `invalid-prompt-leak.appendix.json` — prompt text in `notes` field
  (must be rejected by conformant emitters; readers may accept but
  should warn).

A conformant implementation passes the fixture suite.

## Reference implementation

Halyard's `appendix.py` is the reference implementation for v1. The
verifier at `halyard.dev/verify` is a JavaScript reimplementation
against the same protocol.

External implementations may be written in any language. The protocol
is open. There is no certification, no fee, and no required affiliation
with Halyard or Kormilo LLC.
