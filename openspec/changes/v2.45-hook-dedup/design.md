# v2.45 — Cursor/Gemini Hook Install De-dup: Design

## Detection helper

Reuse the existing normalization idea (`_cc_hook_cmd_key`). Add:

```python
def _is_halyard_hook_cmd(cmd: str) -> bool:
    parts = cmd.split()
    return bool(parts) and Path(parts[0]).name in ("halyard", "halyard.exe")
```

A command is "ours" iff arg0's basename is `halyard`/`halyard.exe`,
regardless of the absolute path. This matches every stale variant
(uv-tool, repo venv, temp/pipx venvs) and never matches another
vendor's command.

## Gemini install (`_do_install_hook_gemini`)

For each event in `_GC_HOOKS`: rebuild the event's block list as

`[blocks with NO halyard hook] + [one fresh halyard block for {exe}]`

A block counts as halyard if any of its `hooks[].command` is a halyard
cmd. This drops every prior halyard block (any path, including dead
ones) and re-adds exactly one with the current `exe`, preserving
non-halyard blocks and their order.

## Cursor install (`_do_install_hook_cursor`)

Same shape, one level flatter: each event list becomes

`[entries whose command is NOT halyard] + [one fresh {exe} entry]`

Preserves the bun/thedotmack entries; collapses the 4 stale halyard
entries to 1.

## Idempotency / messaging

After the rebuild, compare against the pre-image: if nothing changed,
print "already present"; if halyard entries were removed/updated, print
"installed (deduped N stale)". Always a single `_write_settings`.

## Tests

`tests/test_hook_dedup.py`:
- seed `~/.cursor/hooks.json` (patched path) with 4 different-path
  halyard `cursor-session` + a non-halyard bun entry → after install:
  exactly 1 halyard `cursor-session`, the bun entry intact, points at
  the resolved exe;
- gemini settings seeded with 2 duplicate `gc-session` blocks + a
  foreign block → after install: 1 halyard block per event, foreign
  block intact;
- install twice in a row → second run is a no-op ("already present"),
  file unchanged (true idempotency);
- a stale dead-path halyard entry is replaced, not kept.

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
