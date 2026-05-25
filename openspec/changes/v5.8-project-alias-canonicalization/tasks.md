# Tasks — v5.8 Project alias canonicalization

- [x] `attribution.py`: `_ALIASES_PATH`, `load_project_aliases`,
      `canonical_project`, `set_project_alias`.
- [x] `ai_log.parse_sessions`: apply canonicalization at the read boundary
      (local import; after amendment fold; in-place on surfaced sessions).
- [x] Remove `_norm_project` + `_PROJECT_ALIASES` from `dashboard.py`;
      `_overview_panels` groups by `s.project` directly.
- [x] `halyard projects alias <source> <canonical>` / `--list` CLI.
- [x] Tests: canonical_project; load/set round-trip; invalid-TOML empty;
      parse_sessions merges git/Halyard + kormilo/halyard → kormilo:halyard;
      empty-map no-op. Removed test_v57's `_norm_project` test.
- [x] ruff + mypy clean; full suite green (1510 passed).
- [x] Applied the owner's confirmed aliases; verified the aggregate merges to a
      single kormilo:halyard ($4,444.41); git/Halyard + kormilo/halyard gone.
- [x] Roadmap entry 82.
