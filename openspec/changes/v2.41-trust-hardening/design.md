# v2.41 — Trust Hardening: Design

## 1. Pricing: origin pin on the final URL

After `urllib.request.urlopen`, read `resp.geturl()` (the final URL
after any redirects) and assert it parses to scheme `https` with host
`raw.githubusercontent.com`; otherwise raise `PricingFetchError`
**before the body is decoded/parsed**. This neutralizes the actual
threat — accepting attacker content served via a redirect — without
swapping the call site away from `urllib.request.urlopen` (an opener
subclass that *refuses* the redirect was prototyped but it broke the
established test mock surface for no security gain: urllib transiting a
redirect and then us rejecting its origin is equally safe, since the
body is never trusted). `_REMOTE_URL` is a constant derived from
`_REMOTE_HOST`.

## 2. `_halyard_exe()` trust order

Reorder resolution:
1. `shutil.which("halyard")` — the normal, trusted install.
2. resolved `sys.argv[0]` **only if** it lies under a trusted prefix
   (`sys.prefix`, `sys.base_prefix`, or the directory of the running
   `sys.executable`) — i.e. a real venv/site install, not a
   writable/temp drop.
3. fallback to the literal `"halyard"` (PATH at hook-run time).

This stops a symlink/wrapper named `halyard` in a writable dir from
being persisted into tool configs, while preserving the original intent
(embed the venv binary so PATH need not be set at hook time).

## 3. Dashboard constant-time token compare

`import hmac`; replace `submitted_token != _token` with
`not hmac.compare_digest(submitted_token, _token)`. `_extract_token`
already always returns `str`, and `_token` is `str`, so `compare_digest`
is type-safe.

## 4. `cli_hooks`: don't clobber unparseable config

New `_load_existing_settings(settings_path) -> dict[str, Any]`:
- absent → `{}` (nothing to preserve),
- empty/whitespace-only → `{}` (safe to replace),
- parses → the dict,
- non-empty but invalid JSON, or unreadable → raise
  `HookWriteError(settings_path, ...)`.

`HookWriteError` already (a) prints a clean actionable message via
`_run_installer` for explicit `install-hook-*`, and (b) subclasses
`OSError` so the best-effort auto-install path keeps degrading
gracefully (a malformed user config simply isn't auto-modified rather
than being destroyed). The four duplicated
`try: json.loads … except: existing = {}` blocks are replaced with this
helper.

## 5. Docs

Add to `docs/trust-model.md`:
- **Local dashboard**: binds 127.0.0.1 only, Host/Origin/Referer
  validated, token cookie (HttpOnly/SameSite=Strict, 0600 token file),
  POST-only mutations, body-size cap. Explicitly: not exposed beyond
  loopback; a local process with account access can still reach it.
- **Files Halyard writes**: enumerate the tool-config files it creates
  or appends to and state it preserves existing keys and refuses to
  overwrite an unparseable one.

## Tests

`tests/test_v241_trust_hardening.py`:
- pricing: a 302 response raises `PricingFetchError` (no follow); a
  mocked final URL on a foreign host raises.
- `_halyard_exe`: argv[0] under a temp dir is *not* returned (falls back
  to which/literal); a `which` hit is preferred.
- dashboard: wrong token rejected, correct accepted (behavioral parity
  with constant-time compare).
- `cli_hooks`: a non-empty invalid `settings.json` raises
  `HookWriteError` and the file is left untouched; valid + absent +
  empty still work.

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
