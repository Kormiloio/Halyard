# Spec: Local AI-Work Evidence Appendix

## Requirement: Standalone emission, renderer reuse

`halyard evidence` MUST emit the existing
`render_ai_evidence_appendix` output as a self-contained markdown
artifact, independent of invoice rendering, using the same
period/project/client/month filters as `halyard report`. It MUST NOT
introduce a second appendix renderer or a new captured-data format.

### Scenario: parity with invoice-embedded appendix
- GIVEN the same sessions, plans, and timeclock entries for a period
- WHEN `halyard evidence` runs and when an invoice is rendered with
  `include_ai_evidence`
- THEN the appendix body is byte-identical between the two.

## Requirement: Deterministic integrity digest

The artifact MUST end with a footer carrying
`Evidence digest: sha256:<hex>` computed over the canonical appendix
body (everything before the footer, normalised trailing newline).
Identical inputs MUST produce an identical digest; any change to the
body MUST change the digest.

### Scenario: stable digest
- GIVEN one fixed session set
- WHEN the artifact is produced twice
- THEN both digests are identical.

### Scenario: tamper-evident
- GIVEN a produced artifact
- WHEN one character of the body is altered
- THEN `halyard evidence --verify` reports a mismatch.

### Scenario: volatile data excluded
- GIVEN an informational human-readable timestamp is shown
- THEN it appears after the digest footer and does not affect the
  digest.

## Requirement: Honest boundary, no overclaim

The artifact MUST state it is unsigned local evidence whose digest
detects post-hoc modification but does NOT prove authorship, and that
cryptographic attestation is a Halyard Enterprise feature. The OSS
artifact and code MUST NOT claim signing, verification of authorship,
or cross-party trust.

## Requirement: OSS/enterprise boundary

This change MUST NOT add signing, HMAC, public-key material, or
recipient-side verification beyond local re-hash. Those remain in
Kormiloio/Halyard-Enterprise (the moved v2.19). `--verify` is local
recomputation only, requires no key.

## Requirement: Privacy and source-of-truth

The artifact MUST contain only metadata (no prompts, transcripts,
code, or file contents) — the existing appendix guarantee. The
command is read-only w.r.t. `ai-sessions.log`; it writes only to
stdout or an explicit `--out` path, and MUST refuse to overwrite an
existing `--out` file without `--force`.
