# Design

## Module layout

```
src/halyard/
  appendix.py           # Data model, signing, verification
  templates/
    appendix.html.j2    # PDF render via wkhtmltopdf or weasyprint
  keys/                 # NOT in package; generated under ~/.halyard/keys/
web/
  verify/
    index.html          # Static verifier page; also shipped in package
    verify.js
```

## Cryptography

- **Algorithm:** Ed25519 via `cryptography.hazmat.primitives.asymmetric.ed25519`.
- **Key file format:** PKCS#8 PEM for private, raw bytes hex for public.
- **Private key permissions:** `0600`, owner-only.
- **Canonical form for signing:** RFC 8785 (JCS) JSON Canonicalization
  Scheme. Implemented via the existing `jcs` PyPI package.
- **Signature placement:** the `signature` object is added to the JSON
  *after* canonicalization of the unsigned document. Verifiers strip
  `signature`, canonicalize, and verify against the recorded value.
- **Key rotation:** issuer can rotate by running `halyard appendix init
  --rotate`; old key is moved to `~/.halyard/keys/archive/`. Verifiers
  must use the public key referenced by `issuer.public_key_fingerprint`.

We do not roll our own crypto. Every primitive comes from `cryptography`.

## Data flow — generation

```
halyard appendix create --client acme --period 2026-05-01..2026-05-15
  ↓
1. Read halyard.toml for issuer name + recipient defaults
2. Load private key from ~/.halyard/keys/issuer.ed25519
3. Query SQLite cache (v2.14, hardened in v2.18) for sessions in scope
4. Apply v2.17 amendment fold to get latest attribution
5. Hash file paths (only present if collector captured them)
6. Build unsigned JSON document
7. Canonicalize via JCS
8. Sign with Ed25519
9. Embed signature; write JSON
10. Optional: render PDF via Jinja + html-to-pdf
```

## Data flow — verification

```
halyard appendix verify <file>
  ↓
1. Parse JSON; extract `signature`
2. Strip `signature` from document
3. Canonicalize remainder via JCS
4. Look up issuer public key by `issuer.public_key_fingerprint`:
   a. Local key file if available (~/.halyard/keys/known/<fingerprint>.pub)
   b. halyard.dev/keys/<fingerprint> with consent prompt on first fetch
   c. User-provided URL via --pubkey flag
5. Verify signature; print result
```

The web verifier mirrors steps 1-5 in JavaScript using the WebCrypto
API for Ed25519. (WebCrypto Ed25519 has good but recent browser
support; ship a `tweetnacl-js` fallback for older browsers.)

## Data model

See `prd-attestable-appendix.md` for the full schema. Key invariants:

1. **No prompt text.** Type-checked: `appendix.py` raises if any
   field's string content matches heuristics for prompt text (long
   strings with sentence-like structure). Fuzz test covers this.
2. **No raw file paths.** All path fields run through
   `hashlib.sha256(path).hexdigest()` before serialization.
3. **All session counts come from the SQLite cache, not direct log
   reads.** This guarantees consistency with the rest of Halyard's
   reporting.
4. **The signature covers all fields except `signature` itself.**
   `signed_fields` lists what's covered for human inspection; the
   actual cryptographic operation covers the canonicalized JSON minus
   the `signature` object.

## CLI integration

The existing `halyard invoice` command gains a `--with-appendix` flag:

```bash
halyard invoice acme --period 2025-06 --with-appendix
# → writes invoices/2025-06-acme.md
# → writes invoices/2025-06-acme.appendix.json
# → writes invoices/2025-06-acme.appendix.pdf
```

The bundle is what the freelancer sends to the client.

## Web verifier

`halyard.dev/verify/<appendix_id>` is a static page. Implementation:

- Plain HTML + JS, no framework.
- Loads appendix JSON either pasted by the user or fetched from a URL
  in the query string.
- Uses WebCrypto for Ed25519 verification (fallback to `tweetnacl-js`).
- Fetches issuer public key from
  `halyard.dev/keys/<fingerprint>` (CORS-enabled static file).
- Renders human summary: period, hours, cost, tool mix, trust label.
- No analytics, no logging, no cookies.

The same code ships in the Python package as
`src/halyard/web/verify/index.html` so enterprise customers self-host.

## Public key registry

`halyard.dev/keys/<fingerprint>` is a static endpoint serving public
keys uploaded via `halyard appendix publish-key`. Upload requires:

1. CLI prompts for explicit consent.
2. Includes the issuer's name + email (from `halyard.toml`).
3. POST to a sign-in API that returns the URL.
4. The user can revoke at `halyard.dev/keys/manage/<fingerprint>` (auth
   via email link).

For users who don't want to use halyard.dev, the appendix can carry a
`pubkey_url` field pointing to the issuer's own server. Verifiers
fetch from that URL with a consent prompt.

## Performance

- Generation: dominated by the SQLite query. ~100ms for 1000-session
  windows. Ed25519 sign is microseconds.
- Verification: similar; dominated by JCS canonicalization.
- PDF render: ~500ms via weasyprint for a typical appendix.

Total wall time for `halyard appendix create --bundle pdf`: <2 seconds
for a typical case.

## Security

| Threat                                            | Defense                              |
|---------------------------------------------------|--------------------------------------|
| Forged appendix                                   | Ed25519 signature; recipient verifies |
| Modified appendix in transit                      | Signature covers JCS canonical form  |
| Replay (using old appendix as new)                | `appendix_id` is unique; recipient checks they haven't seen it before |
| Stolen private key                                | Rotation command; revocation list at halyard.dev/keys/revoked |
| Compromised halyard.dev                           | Verifier supports user-provided pubkey URL; self-hostable |
| Side-channel leak via PDF metadata                | PDF embedded JSON is the JCS form; no extra metadata leaks |
| Hostile recipient demanding code                  | Privacy contract; protocol design rejects extension; documented |

## Migration

None. v2.19 is purely additive. Existing invoices and AI evidence
appendices continue to work unchanged.

## Threat model boundaries

What this protects:
- Tamper detection.
- Authentication of issuer (key holder).
- Privacy of prompts and code.

What this does not protect:
- Identity claims beyond key ownership ("I am Mario Camaj" requires
  external trust like a published key on a personal website).
- Time-stamping ("this was signed on 2026-05-15" is from the issuer's
  clock; for non-repudiable timestamps, integrate RFC 3161 in v2.20).
- Censorship resistance ("halyard.dev was offline so no one could
  verify"). Self-hostable verifier mitigates.
