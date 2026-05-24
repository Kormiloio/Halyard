# Tasks — v5.2 Codex importer growth-aware re-import

- [x] `codex_app.py`: store `<uuid>\t<size>` in `codex-imported`; reader returns
      `dict[str, int | None]` and parses legacy bare-UUID lines as `None`.
- [x] `codex_app.py`: re-import when file grew / UUID unknown / size unknown;
      skip only when UUID present and size matches.
- [x] `codex_app.py`: tag each imported row with `job_id=codex:<uuid>`.
- [x] `codex_app.py`: save `(uuid, current_size)` for present rollouts; keep the
      prune-to-present-files behavior.
- [x] `ai_log.py`: add `_codex_session_key` + `_redundant_session_key`; route the
      collapse through it (keep `collapse_gemini_sessions` name + behavior).
- [x] Tests: grown rollout re-imports; collapse keeps fuller Codex row; legacy
      bare-UUID re-check; unchanged file skipped.
- [x] Existing v3.14 Gemini collapse tests stay green.
- [x] ruff + ruff format + mypy clean; full suite passing.
