# v5.20 — Tasks

Source: owner pre-release review (2026-06-05); scheduled during the v5.19 audit
as the pre-launch CI/release task. CI/release-process only — no application
source changes.

## Finding 1 — publish.yml becomes a release gate [publish.yml] ✅

- [x] Tag-vs-version invariant: read `pyproject.toml` `project.version` via
      stdlib `tomllib`, compare to `GITHUB_REF_NAME` (leading `v` stripped);
      `::error::` + exit 1 on mismatch, before any build.
- [x] Quality gate mirrors the local/`main` gate: `ruff check .`,
      `ruff format --check .`, `mypy src`, full `pytest -q`.
- [x] `pip-audit --skip-editable` (same form/rationale as ci.yml).
- [x] Artifact audit: `twine check dist/*` (metadata + long-description render).
- [x] Clean-venv install smoke test: build wheel, install into a throwaway
      venv outside the source tree, run `halyard --version`.
- [x] Publish step (`pypa/gh-action-pypi-publish`) reached only if all gates
      pass; trusted-publishing `id-token: write` + `environment: pypi` kept.

## Finding 2 — pin all actions to immutable SHAs [publish.yml, ci.yml, install-test.yml] ✅

- [x] `actions/checkout` → `34e1148…f8d5` (v4.3.1).
- [x] `actions/setup-python` → `a26af69…7065` (v5.6.0).
- [x] `actions/setup-node` → `49933ea…0020` (v4.4.0).
- [x] `pypa/gh-action-pypi-publish` → `cef2210…277b` (v1.14.0), off the
      mutable `@release/v1` branch.
- [x] Each pin carries a `# vX.Y.Z` trailing comment for review/Renovate.
- [x] `grep` confirms zero floating tags / branch refs remain in any `uses:`.

## Finding 3 — VS Code extension CI job [ci.yml] ✅

- [x] New `vscode-extension` job, `working-directory: vscode-extension`.
- [x] `actions/setup-node` (node 20) + npm cache on
      `vscode-extension/package-lock.json`.
- [x] `npm ci` → `npm run compile` → `npm test` → `npm audit
      --audit-level=high` (high/critical hard-fail; moderate dev-only allowed).

## Finding 4 — sdist ships local Hypothesis cache [.gitignore] ✅

- [x] `.hypothesis/` added to the root `.gitignore` (hatchling only honors the
      root ignore file, not the self-ignoring one Hypothesis writes inside its
      cache dir — see design.md).
- [x] Rebuild after a full `pytest` run verified: sdist 1162 → 809 files, zero
      `.hypothesis` entries, `twine check` PASSED.
- [x] Explicit `[tool.hatch.build.targets.sdist]` include list (root-anchored
      globs): `/src/halyard`, `/tests`, `/samples`, `/CHANGELOG.md`,
      `/SECURITY.md`. Sdist now 279 files / 570 KB (was 1162 / 1.58 MB).
- [x] From-sdist install verified in a clean venv: `pip install
      halyard-0.2.1.tar.gz` → `halyard --version` → `halyard 0.2.1`.

## Gate ✅

- [x] All three workflow files parse as valid YAML.
- [x] Extension job verified locally: ci/compile/test (28 passed) / audit (0
      vulns) green.
- [x] Publish gate verified locally: version-match logic, `python -m build`,
      `twine check` PASSED, clean-venv wheel install → `halyard 0.2.1`.
- [x] Roadmap entry added to `openspec/project.md`.
