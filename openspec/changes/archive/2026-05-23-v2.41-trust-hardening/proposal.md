# v2.41 — Trust Hardening (residual review items)

## Problem

The independent security review left a batch of lower-severity, real
hardening items that did not fit v2.39 (input injection) or v2.40
(authenticated state). They share a theme: trust boundaries that are
*mostly* fine but have a sharp edge or an undocumented assumption.

1. **MEDIUM — Pricing fetch follows redirects with no host pin.**
   `update_pricing()` uses `urllib.request.urlopen`, which silently
   follows HTTP redirects. A redirect off `raw.githubusercontent.com`
   would be fetched and (combined with TOFU + `--accept-changed`) could
   serve attacker content. Fixed URL keeps severity bounded, but
   redirect-following is gratuitous attack surface.

2. **MEDIUM — `_halyard_exe()` trusts `sys.argv[0]` first.** It embeds
   the resolved `argv[0]` into every tool's hook config as the command
   to run on each session. If `halyard` is invoked via a symlink/wrapper
   in a writable dir, that path is persisted as a per-session executed
   command — a persistence primitive.

3. **MEDIUM — Dashboard token compared with `!=`.** Non-constant-time
   comparison is a (weak, local) timing side-channel for a security
   token.

4. **LOW — `cli_hooks` clobbers unparseable user config.** On
   `JSONDecodeError` it resets `existing = {}` and then *overwrites* the
   file — destroying a user's hand-maintained `settings.json` (e.g. one
   with JSONC comments that Claude/Cursor tolerate).

5. **DOC — Trust model is silent on two posture facts.**
   `docs/trust-model.md` never states that the dashboard is
   127.0.0.1-only or that Halyard writes into user tool-config files
   (`~/.claude`, `~/.gemini`, `~/.cursor`, VS Code tasks).

## Goals

- No redirect-following and an explicit final-host check on the pricing
  fetch.
- Executable path resolved by `which` first; `argv[0]` only trusted when
  it resolves under a trusted prefix.
- Constant-time dashboard token comparison.
- Never overwrite a non-empty unparseable user config — fail with the
  existing actionable `HookWriteError` instead.
- Document the dashboard-local-only posture and the config-write scope.

## Non-goals

- Pricing supply-chain signing (asymmetric/manifest) — larger, separate.
- Changing the dashboard bind address or auth model (already sound).

## Out of scope

No new commands or formats. Hardening + documentation only.
