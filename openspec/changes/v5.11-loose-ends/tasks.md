# Tasks — v5.11 Loose ends

- [x] `attribution.load_project_aliases(project_dir=None)`: merge committed
      `<project_dir>/project-aliases.toml` + home; cache on both mtimes.
- [x] `attribution.set_project_alias(..., project_dir=None)`: write committed
      file when project dir known.
- [x] Callers pass `project_dir`: `ai_log.parse_sessions`, `budget`,
      `invoicing`, `hub_server`; `cli_projects alias` resolves + passes it.
- [x] Gitignore `project-aliases.toml` (+ `time.timeclock.bak*`) in the product
      repo so the dev's personal aliases/backups don't leak into OSS. (Real user
      projects commit it — the init template never ignored ledger data.)
- [x] `ai_log.log_diagnostic`: flatten newlines in msg/tool/project.
- [x] `conftest._isolate_halyard_logs`: redirect `_HALYARD_DIAG_LOG` +
      `_HALYARD_AUDIT_LOG` to tmp for all tests.
- [x] `ci.yml`: non-blocking `test-windows` job (pytest on windows-latest).
- [x] Tests (`test_v511_loose_ends.py`): alias merge/precedence/cache,
      committed write, log newline, real-log untouched.
- [x] ruff + ruff format + mypy clean; full pytest green.
- [x] project.md roadmap entry; commit.
