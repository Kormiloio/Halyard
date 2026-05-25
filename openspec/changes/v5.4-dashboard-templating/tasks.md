# Tasks — v5.4 Dashboard templating + timezone ADR

- [x] Add `src/halyard/templates/dashboard.html.j2` reproducing the page chrome
      and per-panel scaffolding with `|safe` placeholders.
- [x] `dashboard.py`: add cached `_dashboard_template()` (lru_cache,
      `FileSystemLoader`, `autoescape=True`); `Template` under `TYPE_CHECKING`.
- [x] `dashboard.py`: replace the `_render_state` f-string with a context dict
      (same helper calls) + `template.render(**context)`.
- [x] `docs/adr/0001-timezone-model.md` + `docs/adr/README.md` index.
- [x] Tests: `tests/test_v54_dashboard_templating.py` (template ships, env
      cached, chrome markers + fragments present).
- [x] All 100 existing dashboard tests pass unchanged.
- [x] ruff + ruff format + mypy clean on changed files.
- [x] Verify template ships in the wheel (hatchling already globs
      `templates/*.j2`).
- [x] Update `openspec/project.md` roadmap with the v5.4 entry.
