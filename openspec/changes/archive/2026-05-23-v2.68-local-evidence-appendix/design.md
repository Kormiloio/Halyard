# v2.68 — Local AI-Work Evidence Appendix: Design

> Spec only — proposed, not started. OSS slice of the
> enterprise-moved v2.19. Awaiting alignment on proposal before code.

## Audit (what already exists — do not duplicate)

- `invoicing.py:render_ai_evidence_appendix(sessions, plans,
  tc_entries, period_label)` already produces the full markdown:
  metrics table, cost-basis table with captured/allocated/inferred
  notes, and the v3.0 `_render_pr_refs_subsection`. **Reuse it
  verbatim** — v2.68 adds emission + digest *around* it, no second
  renderer.
- It is currently reachable only via `invoicing.py:225`
  (`include_ai_evidence`) during invoice render. No standalone path,
  no integrity marker.

## Command

`halyard evidence` (registered in `cli_report.py`, the
reporting/analytics sub-app — same home as `report`/`dashboard`):

```
halyard evidence [--all] [--project SLUG] [--client SLUG]
                  [--month YYYY-MM] [--ledger] [--out PATH]
```

- Resolves the project dir like `report` (`find_project_dir()`),
  same filter flags for parity. Selects sessions + plans + timeclock
  entries for the period, calls `render_ai_evidence_appendix`.
- Default: write the artifact to stdout. `--out PATH`: write the file
  (no-silent-write rule — this is the artifact the user explicitly
  asked for, not ledger data; an existing `--out` path is refused
  unless `--force`).
- Read-only w.r.t. the ledger; never mutates `ai-sessions.log`.

## Integrity digest

A footer appended after the appendix body:

```
<appendix body>

---
Evidence digest: sha256:<hex>
Unsigned local evidence — the digest detects post-hoc modification of
this artifact; it does not prove authorship. Cryptographic
attestation is a Halyard Enterprise feature.
```

`digest = sha256(canonical_body.encode("utf-8"))` where
`canonical_body` is the appendix string **up to and excluding the
digest footer**, with a normalised trailing newline. Determinism
rules:

- The appendix already sorts tools/models and groups PR refs
  deterministically; numeric formatting is fixed-width — no change
  needed.
- No wall-clock "generated at" line is inside the hashed region. If a
  human-facing timestamp is shown, it is printed **after** the digest
  footer (outside the hash) and labelled as informational.
- A `verify` helper (`halyard evidence --verify PATH`) re-derives the
  digest from the file's body and reports match/mismatch — pure local
  recomputation, **no keys** (still OSS-safe; this is the same
  re-hash anyone could do by hand).

## Module

`evidence.py` (new, small): `build_evidence_artifact(...) -> str`
(compose renderer + footer + digest) and
`verify_evidence_artifact(text) -> bool` (split body/footer, re-hash,
compare). `cli_report.py` gets a thin command wrapper. No new data
format, no schema change.

## Tests (`tests/test_v268_local_evidence_appendix.py`)

1. `halyard evidence` emits the same appendix body as the
   invoice-embedded path for the same inputs (renderer reuse proof).
2. Digest is deterministic: same sessions ⇒ identical `sha256:`
   across two runs; a one-token change ⇒ different digest.
3. `--verify` returns success on an unmodified artifact, failure when
   one character of the body is altered.
4. Volatile data outside the hash: any informational timestamp is
   after the footer and does not affect the digest.
5. Privacy: artifact contains no prompt/code/transcript fields (same
   guarantee as the existing appendix) — assert on a fixture with a
   noted session.
6. Honest-boundary string present; **no** signing/verification/key
   language (grep-style assertion that the OSS artifact never claims
   authorship proof).
7. `--out` refuses to overwrite without `--force`; writes exactly the
   stdout content otherwise.

## Docs

`docs/PRD-ai-work-ledger.md` "What Is Captured"/evidence section gains
the standalone `halyard evidence` artifact + the digest's exact
guarantee (tamper-evident, not authorship). `docs/trust-model.md`
"In attestable appendices" updated to distinguish the OSS unsigned
self-digest from the enterprise signed appendix (consistent with the
v2.40 honest-claims framing).

## Gate

`pytest` + `ruff` + `ruff format --check` + `mypy src/`. Roadmap entry
(reinstates v2.19 as its OSS slice = v2.68; the signed feature stays
enterprise). Feature changeset (new command) — full spec.

## Relationship to v2.19

v2.19 (signed/verifiable/cross-party) **stays in
Kormiloio/Halyard-Enterprise**. v2.68 is only the solo-user emit +
self-digest floor that legitimately belongs in OSS and that the
enterprise signed version layers on top of. No code crosses repos.
