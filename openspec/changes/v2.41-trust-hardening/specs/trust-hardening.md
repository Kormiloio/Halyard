# Spec — Trust hardening

## Requirement: Pricing fetch is origin-pinned

WHEN `update_pricing()` fetches the remote table
THEN the response's final URL (after any redirects) MUST be scheme
`https` with host `raw.githubusercontent.com`, else `PricingFetchError`
is raised **before the body is parsed or trusted**.
SO THAT a redirect to a foreign origin cannot feed attacker-controlled
pricing content, even though `urllib` may transit the redirect.

## Requirement: Executable path is resolved trustworthily

WHEN hook configs are written with the halyard command path
THEN the path MUST come from `shutil.which("halyard")` when available,
OR from `sys.argv[0]` only when it resolves under a trusted prefix
(`sys.prefix`, `sys.base_prefix`, or the `sys.executable` directory),
OTHERWISE fall back to the literal `"halyard"`.
SO THAT a `halyard`-named binary in a writable directory cannot be
persisted into tool configs.

## Requirement: Dashboard token comparison is constant-time

WHEN the dashboard validates a submitted token on POST
THEN it MUST use a constant-time comparison (`hmac.compare_digest`).

## Requirement: User config is never clobbered

WHEN Halyard updates a tool settings file that exists and is non-empty
but does not parse as JSON
THEN it MUST raise `HookWriteError` (clean message for explicit
installs; graceful skip on the best-effort path) and MUST NOT overwrite
the file.
WHEN the file is absent or empty
THEN it is treated as `{}` and written normally.

## Requirement: Trust model documents posture

`docs/trust-model.md` MUST state that the dashboard binds only to
127.0.0.1 (not exposed beyond loopback; a local account-level process
can still reach it) and MUST enumerate the user tool-config files
Halyard creates or appends to, noting it preserves existing keys.
