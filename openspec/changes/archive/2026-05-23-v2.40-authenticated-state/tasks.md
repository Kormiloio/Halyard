# v2.40 — Authenticated State Integrity: Tasks

- [x] `IntegrityMode` += `"hmac"`; toml + env resolution accept it
- [x] `_integrity_key(create=…)` — 0600 atomic key at
  `~/.halyard/integrity.key`, fail-closed on read
- [x] `_sidecar(path, mode)` — `.sha256` for hash, `.hmac` for hmac
- [x] `read_trusted_state` / `write_trusted_state` hmac branch
  (constant-time compare, sidecar-first write)
- [x] Rewrite `state_integrity.py` docstring with the honest 3-tier
  guarantee (delete "resists local-account attacks")
- [x] `docs/trust-model.md` — document off/hash/hmac precisely + recovery
- [x] PRD integrity section synced to the honest claim
- [x] `halyard doctor` recommends `hmac` when mode is `hash`
- [x] Regression tests (`tests/test_v240_authenticated_state.py`)

## Gate

- [x] `pytest` green (1003 passed)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md` (item 19)

- [x] PRD/ARD reviewed — no active PRD/ARD mentions state integrity; the authoritative honest claim now lives in the code docstring, `docs/trust-model.md`, and `specs/authenticated-state.md`.
