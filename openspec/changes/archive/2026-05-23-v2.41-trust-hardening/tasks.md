# v2.41 — Trust Hardening: Tasks

- [x] #1 pricing: origin-pin the final URL (`pricing.py`)
- [x] #2 `_halyard_exe()` trust order: which → trusted-prefix argv[0] →
  literal (`cli_hooks.py`)
- [x] #3 dashboard constant-time token compare (`dashboard.py`)
- [x] #4 `_load_existing_settings` — never clobber unparseable config;
  replace 4 duplicated blocks (`cli_hooks.py`)
- [x] #5 `docs/trust-model.md`: dashboard-local-only + config-write scope
- [x] Regression tests (`tests/test_v241_trust_hardening.py`)

## Gate

- [x] `pytest` green (1014 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 20)

- [x] PRD/ARD reviewed — no active PRD/ARD claims affected; trust posture documented in `docs/trust-model.md` and `specs/trust-hardening.md`.
