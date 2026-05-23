# v2.68 — Local AI-Work Evidence Appendix (OSS slice of v2.19)

## Problem & scope origin

v2.19 ("attestable AI work appendix" — signed, verifiable,
cross-party) was **moved out of OSS scope to
Kormiloio/Halyard-Enterprise on 2026-05-14**: cryptographic
attestation is a bottoms-up *enterprise* feature whose value rises
with cross-party verification (a recipient trusting a signed
artifact). That move is correct and stands.

But there is a **solo-user slice that legitimately belongs in OSS**
and is not yet delivered. Today the AI-usage evidence appendix
(`render_ai_evidence_appendix`, `invoicing.py:253`) is rich —
metrics, cost basis with honest trust notes, v3.0 PR-linked
artifacts — but it is **only emitted embedded inside an invoice**
(`include_ai_evidence`). A freelancer who wants to attach proof of
AI-assisted work to a *non-invoice* deliverable (a PR description, a
status report, a scope doc) has no way to produce it, and the
artifact carries **no integrity marker** so the author cannot even
detect their own post-hoc edits.

## Goal

Ship the OSS-safe, single-user half: a standalone, self-contained
evidence artifact with a deterministic integrity digest — **without**
crossing into the enterprise-moved territory (no keys, no signatures,
no PKI, no cross-party trust).

- **`halyard evidence`** — a new read-only command that emits the
  existing appendix as a standalone markdown artifact for a chosen
  period/project, independent of any invoice. Reuses
  `render_ai_evidence_appendix` (no duplicate renderer).
- **Deterministic integrity digest** — a `sha256:` over the
  canonicalised appendix body, emitted as a footer line. This is
  tamper-**evident** (the author can quote/publish the digest; anyone
  can re-hash the file to confirm it was not altered), not
  tamper-**resistant** and not authorship proof. Mirrors the v2.40
  honesty discipline: the artifact states exactly what the digest
  does and does not prove.
- **Honest boundary statement** in the artifact: "Unsigned local
  evidence. The digest detects post-hoc modification; it does not
  prove who produced it. Cryptographic attestation is a Halyard
  Enterprise feature." No overclaiming, no enterprise upsell surface
  beyond this one factual sentence.

## Constraints honored

- **OSS/enterprise split intact.** No signing/verification/key
  material here — that stays in the enterprise repo. This is only the
  standalone-emit + self-digest a single user can use alone.
- **Privacy contract.** Same as the existing appendix: no prompts, no
  transcripts, no code, no file contents. Metadata only.
- **Trust labels preserved.** The appendix's existing
  captured/allocated/inferred notes are unchanged; the digest is a
  new, clearly-scoped integrity marker, not a trust upgrade.
- **Files are the source of truth.** Pure read + emit; the command
  writes only the artifact the user asks for (to stdout or an
  explicit `--out` path), nothing to the ledger.
- **Deterministic.** Identical inputs ⇒ identical digest: stable sort,
  fixed numeric formatting, and exclusion of volatile fields (e.g. a
  "generated at" wall-clock line is outside the hashed region).

## Non-goals

- Signing, HMAC, public-key verification, or any cross-party trust
  (enterprise — explicitly out).
- A new appendix format or new captured data — this is emission +
  digest over the existing renderer.
- Revoking/altering v3.0's invoice-embedded appendix (kept as-is;
  `halyard evidence` is additive and shares the renderer).

## Out of scope

Enterprise aggregation, recipient-side verification tooling, and a
published verification spec — those live with the moved v2.19 in the
enterprise repo and gate on cross-party pull.
