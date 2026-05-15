# v2.45 — Cursor/Gemini Hook Install De-dup

## Problem

`_do_install_hook_cursor` and `_do_install_hook_gemini` decide a hook is
"already present" by **exact command-string match**, where the command
embeds the absolute halyard binary path (`{exe} cursor-session`). Every
distinct install path is a different string, so each install **stacks
another entry** instead of replacing the prior one.

Observed in the wild: `~/.cursor/hooks.json` accumulated **four**
`halyard cursor-session` commands (global uv-tool, repo venv, a deleted
`/private/var/folders/.../T/...` test venv, a `/private/tmp/pipx-test`
venv) and `~/.gemini/settings.json` had the gemini hook registered
twice. Result: every session fires the collector multiple times,
appending duplicate placeholder sessions (cursor `2000/400`, gemini
`100/50`, `$0.00`, `source=hook`) — phantom "Cursor" usage the user
never generated, inflating "Sessions Adrift".

Claude's installer already normalizes via `_cc_hook_cmd_key` (basename
of arg0 + subcommand) so it is idempotent across paths. Cursor and
Gemini do not. This brings them to parity and makes install
**self-healing**: a stale/dead-path halyard hook is replaced, not
duplicated.

## Goals

- `install-cursor-hook` / `install-gemini-hook` are idempotent across
  differing absolute halyard paths.
- Re-running install (from any install) leaves **exactly one** halyard
  hook per event, pointing at the current binary.
- Stale halyard entries (old/dead venv paths) are removed on install.
- Non-halyard hooks (other vendors' entries) are preserved untouched.

## Non-goals

- Changing what the collectors record, or the placeholder-token
  behavior at SessionStart (separate concern).
- Touching Claude's installer (already correct).
- Cleaning the user's existing polluted log (done operationally,
  out of band).

## Out of scope

The `gemini-hook-reapply` launchd glue is user-local machine setup, not
shipped code.
