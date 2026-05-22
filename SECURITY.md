# Security Policy

Halyard is a local-first tool: it reads logs, transcripts, and config
files on the user's machine and writes session metadata to that same
machine. The privacy and integrity of that local data is the project's
core promise. We take security reports seriously.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security reports.**

Use GitHub's private vulnerability reporting:

1. Go to the repository's [Security tab](https://github.com/Kormiloio/Halyard/security).
2. Click **Report a vulnerability**.
3. Fill in the advisory form with as much detail as you can — the
   shorter the time to a working repro, the faster we can fix it.

If you cannot use GitHub Security Advisories for any reason, open an
issue titled "Security contact request" (no details) and a maintainer
will follow up off-list.

## What to include

A useful report typically has:

- The Halyard version (`halyard --version`) and Python version.
- The platform (macOS / Linux distro).
- A minimal reproduction — config files, environment, steps.
- The expected vs. observed behavior.
- The privacy / integrity / availability impact you see (e.g. "this lets
  another local process forge a session attribution").

Proof-of-concept code is welcome but not required.

## Scope

In scope:

- The Halyard CLI, hooks, collectors, dashboard, and packaged templates.
- The on-disk state under `~/.halyard/` and the integrity sidecars.
- Anything published to PyPI as `halyard`.

Out of scope:

- Vulnerabilities in upstream dependencies (please report those
  upstream; we will bump versions once a fix is available).
- Configuration mistakes specific to a single user's environment that
  don't generalize.
- Issues that require an attacker to already have full local-account
  access — Halyard's threat model treats the local account as trusted.
  (See `docs/security-architecture-review-2026-05-08.md` for the
  documented assumptions.)

## Response

We aim to:

- Acknowledge the report within **3 working days**.
- Confirm or refute the issue within **10 working days**.
- Ship a fix or a documented mitigation before publicly disclosing.

We do not currently run a paid bug bounty program. Reporters who want
public credit will be named in the release notes for the fixing
version; reporters who prefer to stay anonymous will be respected.

## Supported versions

Halyard ships from `main`. Only the most recent published release on
PyPI receives security patches; users on older releases should
upgrade. There are no LTS branches.
