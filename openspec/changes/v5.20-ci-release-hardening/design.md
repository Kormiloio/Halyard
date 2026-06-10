# v5.20 — Design

## publish.yml — single-job release gate

The publish job already carried `environment: pypi` + `permissions:
id-token: write` for trusted publishing. Trusted publishing needs the OIDC
token and the built `dist/` in the **same** job, so the gate stays a single
sequential job rather than a `needs:`-chained fan-out — the artifacts and the
credential never have to cross a job boundary.

Step order (fail-fast cheapest-first, build only once the tree is known-good):

1. checkout → setup-python 3.12 → `pip install -e ".[dev]" build twine`
   (`[dev]` brings ruff, mypy, pytest, pip-audit; `build`/`twine` are the
   release-only tools).
2. **Tag-vs-version check** — read `project.version` from `pyproject.toml` via
   stdlib `tomllib`, strip the leading `v` from `GITHUB_REF_NAME`, compare.
   Mismatch → `::error::` + exit 1. This is first after install so a mistagged
   release dies before any expensive work.
3. ruff check · ruff format --check · mypy src · `pytest -q` (full suite — the
   Textual pilot tests are runnable since the v5.19 `tick=True` freeze fix).
4. `python -m build` (sdist + wheel).
5. `pip-audit --skip-editable` — same form and rationale as `ci.yml` (inspect
   the installed env in place; skip the local editable halyard so pip-audit
   does not try to re-resolve it from a git URL).
6. `twine check dist/*` — validates artifact metadata and that the README
   renders as the PyPI long description.
7. **Clean-venv install smoke test** — `python -m venv` under `/tmp`, install
   the built wheel (not editable, source not on path), run `halyard --version`.
   This is the gate that catches an un-importable build or a missing packaged
   data file (the v2.16 `templates/` class of bug).
8. `pypa/gh-action-pypi-publish` — only reached if 2–7 all pass.

### Rejected alternatives

- **Split quality-gate + publish jobs.** Would force passing `dist/` via
  `upload-artifact`/`download-artifact` and re-establishing the OIDC context;
  more moving parts for no benefit at this scale.
- **Re-run the full 3.11–3.13 matrix in the gate.** `ci.yml` already runs the
  matrix on merge to `main`. The release gate re-checks the tagged tree on the
  one Python that builds/publishes (3.12); a full matrix here is redundant
  wall-clock on the release path.

## SHA pinning

Every `uses:` pinned to the commit the tag pointed at on 2026-06-06, resolved
via the GitHub refs API and recorded with a `# vX.Y.Z` trailing comment:

| Action | Commit SHA | Version |
| --- | --- | --- |
| `actions/checkout` | `34e114876b0b11c390a56381ad16ebd13914f8d5` | v4.3.1 |
| `actions/setup-python` | `a26af69be951a213d495a4c3e4e4022e16d87065` | v5.6.0 |
| `actions/setup-node` | `49933ea5288caeca8642d1e84afbd3f7d6820020` | v4.4.0 |
| `pypa/gh-action-pypi-publish` | `cef221092ed1bacb1cc03d23a2d87d1d172e277b` | v1.14.0 |

`pypa/gh-action-pypi-publish` previously used the `@release/v1` **branch** —
the most dangerous reference of all (mutable, moving, and holding the publish
credential). Pinned to the commit at the `release/v1` head, which is the
`v1.14.0` tag.

## vscode-extension CI job

A third job in `ci.yml`, parallel to the Python jobs:

- `defaults.run.working-directory: vscode-extension` so every `run:` executes
  in the package; `uses:` steps still run at repo root (checkout + setup-node).
- `actions/setup-node` with `node-version: "20"` and npm cache keyed on
  `vscode-extension/package-lock.json` (the cache path is repo-root-relative,
  hence the explicit prefix).
- `npm ci` (lockfile-exact) → `npm run compile` (`tsc -p ./`) → `npm test`
  (`vitest run`) → `npm audit --audit-level=high`.
- **Audit level = high, deliberately.** Fail on high/critical only. Moderate
  dev-only advisories (e.g. the esbuild advisory that has reached the tree via
  vitest) never ship in the `.vsix` — `.vscodeignore` excludes `src/**` and
  `node_modules/**` — so gating the build on a moderate dev-tool advisory would
  be noise. High/critical still hard-fail.

## Verification performed locally (2026-06-06)

- All three workflow files parse as valid YAML; `grep` confirms zero remaining
  floating tags / branch refs in any `uses:`.
- `npm ci` · `npm run compile` · `npm test` (28 passed) · `npm audit
  --audit-level=high` (0 vulns) green in `vscode-extension/`.
- Tag-vs-version logic verified: matches `v0.2.1` against pyproject `0.2.1`,
  rejects `v9.9.9`.
- `python -m build` → `twine check` (PASSED) → clean-venv install of the built
  wheel → `halyard --version` prints `halyard 0.2.1`.

## Finding 4 — sdist ships the local Hypothesis cache (found 2026-06-09)

Running the full launch-readiness sequence in `publish.yml`'s exact order
(`pytest` then `python -m build`) contaminated the sdist with 353
`.hypothesis/` example-database cache files. Hypothesis self-ignores its cache
by writing a `.gitignore` containing `*` *inside* `.hypothesis/`; git honors
nested ignore files, but hatchling's default sdist file selection only applies
the root `.gitignore`, so the cache shipped in the release artifact. `twine
check` does not catch this — the metadata is valid, the contents are wrong.

Fix, part 1: `.hypothesis/` added to the root `.gitignore`. Rebuild verified:
sdist 1162 → 809 files, zero `.hypothesis` entries, wheel unchanged (the wheel
only ever packaged `src/halyard`), `twine check` still PASSED.

Fix, part 2 — explicit sdist contents. Even ignoring the cache, hatchling's
default selection shipped the whole repo (455 `openspec/` files, `docs/`,
`vscode-extension/`, `uv.lock`, agent config). `[tool.hatch.build.targets.sdist]`
now lists exactly what a from-source build and test run need: `/src/halyard`,
`/tests`, `/samples` (asserted to exist by `test_v41_polyglot`), `/CHANGELOG.md`,
`/SECURITY.md`; hatchling auto-includes `pyproject.toml`, README, and LICENSE.
Patterns are root-anchored (leading `/`) because hatchling treats them as
git-style globs — unanchored `samples` also matched `docs/samples/`. Rebuild
verified: 279 files / 570 KB (from 1162 / 1.58 MB), `twine check` PASSED, and
the sdist installs in a clean venv (`pip install halyard-0.2.1.tar.gz` →
`halyard --version` → `halyard 0.2.1`), which exercises the sdist→wheel path.
