# Design — v5.8 Project alias canonicalization

## Storage
`~/.halyard/project-aliases.toml`:
```toml
[aliases]
"git/Halyard" = "kormilo:halyard"
"kormilo/halyard" = "kormilo:halyard"
```
Dedicated file (not `repos.toml`): different concept (canonicalization vs.
attribution-derivation) and `_write_repos_config` only emits `[repos]`, so a
shared file would drop aliases on the next `register_repo`.

## `attribution.py`
- `_ALIASES_PATH = Path.home()/".halyard"/"project-aliases.toml"` (module
  constant → monkeypatchable in tests / for hermeticity).
- `load_project_aliases() -> dict[str,str]` — tolerant read (`{}` on
  missing/invalid TOML), only `str→str` entries kept.
- `canonical_project(slug, aliases) -> str | None` — `None`→`None`; else
  `aliases.get(slug, slug)`. Single-hop (the map is direct); a self-referential
  or cyclic entry just resolves to itself (no infinite loop).
- `set_project_alias(source, canonical)` — round-trips via `tomli_w` (injection-
  safe, like `_write_repos_config`), sorted keys, creates the dir.

## Apply point (`ai_log.parse_sessions`)
After the amendment-fold loop and before the return, with a **local import**
(attribution imports ai_log at module level, so the reverse must be local —
same pattern as the existing `from halyard.collectors import …` in
`parse_sessions`):
```python
from halyard.attribution import canonical_project, load_project_aliases
aliases = load_project_aliases()
if aliases:
    for sess in surfaced:
        if sess.project:
            sess.project = canonical_project(sess.project, aliases)
```
`AiSession` is mutable (amendments already mutate it), so in-place assignment is
fine. Identity (`session_hash`/`_raw_hash`) is computed from the raw line before
this, so canonicalization never affects dedup/amendment joins. Applied to the
final surfaced list so synthetic/future-row filters (which key on `project is
None` / dates) are unaffected.

## Dashboard cleanup
Remove `_norm_project` + `_PROJECT_ALIASES` from `dashboard.py`; `_overview_panels`
groups by `s.project` directly (already canonical from `parse_sessions`). Update
`test_v57` (its `_norm_project` test moves to `canonical_project` coverage).

## CLI
`halyard alias-project <source> <canonical>` writes an entry; `--list` prints the
map. Minimal, mirrors `link-repo`.

## Tests
`canonical_project` (passthrough, alias hit, None); `load`/`set` round-trip
(monkeypatched path); `parse_sessions` canonicalizes a log with `git/Halyard` +
`kormilo/halyard` into `kormilo:halyard` (monkeypatched alias path); empty-map
is a no-op (byte-identical behavior).
