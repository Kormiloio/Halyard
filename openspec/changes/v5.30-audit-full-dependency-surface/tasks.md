# v5.30 — Tasks

## Code

- [x] `.github/workflows/ci.yml`: `pip install -e ".[dev,all]"` so
      `pip-audit` covers the optional surface. Kept inside the matrix —
      resolution is version-dependent (v5.29's setuptools case).
- [x] `pyproject.toml`: `mcp>=1.28.1,<2` in both the `mcp` and `all`
      extras. Lower bound clears PYSEC-2026-3481/3482/3483; upper bound
      keeps `mcp.server.fastmcp` importable.
- [x] `uv lock --upgrade` — clears all 27 advisories for local dev.
- [x] `cli_mcp.py`: separate "not installed" from "installed but
      incompatible"; surface the underlying import error.

## Tests (`tests/test_v530_audit_surface.py`)

- [x] Both extras exclude mcp 2.0.0 and 2.1.1.
- [x] Both extras exclude the vulnerable 1.27.1 and admit 1.29.1.
- [x] Incompatible SDK → "not compatible", never "not installed".
- [x] Absent SDK → "not installed", never "not compatible".
- [x] CI installs the extras it audits (guards a revert of the install
      line).

## Empirical verification (not inspection)

- [x] 3.11 venv built the CI way audits clean.
- [x] Same venv resolved mcp 2.1.1 pre-pin; `halyard mcp` failed to start.
- [x] Post-pin resolves mcp 1.29.1; `halyard mcp` answers `initialize`.
- [x] setuptools resolves to 84.0.0 on 3.11, clearing the 83.0.0 floor —
      confirms v5.29's companion CI fix on the leg that was red.
- [x] Full suite passes against the upgraded pins.

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Gates

- [x] `uv run pytest`
- [x] `uv run ruff check .` and `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Out of scope (recorded, not done)

- [ ] Switch CI to `uv sync --locked` so the lock and CI cannot diverge.
      Today CI re-resolves from PyPI and ignores `uv.lock` entirely, so a
      stale lock leaves local dev vulnerable while CI stays green —
      exactly what happened here.
- [ ] Support both mcp majors behind a compatibility import, instead of
      pinning `<2`.
