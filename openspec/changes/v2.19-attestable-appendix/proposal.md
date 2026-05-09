# Proposal: v2.19 — Attestable AI Work Appendix

## Why

Halyard's commercial strategy depends on bottoms-up adoption: ICs install
the OSS, value crosses a team boundary, the team adopts paid Team plans,
the company eventually adopts Enterprise. This loop only fires if there
is a feature whose **value increases when other people also use Halyard**.

Today, no such feature exists. Every install is an island.

The attestable AI work appendix is the network-effect feature: a
cryptographically signed, recipient-verifiable artifact that an IC
attaches to an invoice or deliverable. Recipients verify it without
seeing prompts or source code. Once a recipient experiences the trust
benefit, they ask other contractors and eventually their own team to
also use Halyard.

Strategic anchor: `strategy/commercial-strategy.md` and
`strategy/prd-attestable-appendix.md`.

## What changes

- New CLI subcommand `halyard appendix` with verbs:
  - `init` — generate Ed25519 keypair under `~/.halyard/keys/`.
  - `create` — generate a signed appendix for a client/project/period.
  - `verify` — verify a local appendix file.
  - `publish-key` — upload public key to `halyard.dev/keys/` (consent-gated).
- New module `src/halyard/appendix.py` containing the data model, signing,
  and verification logic.
- New Jinja template `src/halyard/templates/appendix.pdf.j2` (or HTML for
  PDF render) for human-readable PDF wrapping.
- New static verifier site under `web/verify/` (HTML + JS, no backend),
  also shipped in the Python package for self-host.
- Optional integration with `halyard invoice`: the existing AI evidence
  appendix can now ship as a signed companion file.

## What stays the same

- Plain-text logs remain the source of truth.
- No prompt or source-code capture under any circumstance.
- All collectors, reports, and existing CLI surface unchanged.
- The privacy contract from existing surfaces is extended to the
  appendix: hashed paths only, no file contents, no analytics on the
  verifier.

## Out of scope

- GPG / OpenPGP signing (deferred to v2.20 if requested).
- Blockchain anchoring or time-stamping authority integration.
- Identity verification claims beyond key ownership.
- Hosted appendix storage. Issuers store the file; recipients receive it.
- Outcome graph data in the appendix (added additively in v3.0).

## Prerequisites

v2.16, v2.17, v2.18 must ship first:

- v2.16 — security baseline (templates packaged, dashboard auth) so the
  appendix doesn't ship on broken foundations.
- v2.17 — correction-record format. The appendix's session listing is
  derived from the post-fold view of the log; without v2.17, the listing
  could include stale attribution.
- v2.18 — schema migrations + content-addressed cache. The appendix
  generator queries the SQLite cache for the session list; the cache
  must be reliable.

## Success criteria

- A user runs `halyard appendix init` once, then
  `halyard appendix create --client acme --period 2026-05-01..2026-05-15`,
  and gets a valid signed JSON appendix in under 10 seconds for a typical
  90-day window.
- The appendix verifier (CLI and web) confirms the signature against the
  issuer's public key.
- A privacy fuzz test confirms no source code, prompt text, or unhashed
  file paths appear in the appendix output across 1000 randomized
  session inputs.
- An independent verifier (using `pyca/cryptography`) confirms our
  Ed25519 signatures are correct.
- A self-hosted verifier runs from `file://` with no network access
  after the issuer's public key is loaded.
- One design partner sends a real appendix to a real client during
  v2.19 testing; the client successfully verifies it.
