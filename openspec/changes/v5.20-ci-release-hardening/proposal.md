# v5.20 — CI & release-workflow hardening

## Why

The pre-release review (2026-06-05) found the GitHub Actions release/CI
workflows are the last unhardened launch surface. Three gaps, all in
`.github/workflows/`:

1. **`publish.yml` is a blind upload.** A pushed `v*.*.*` tag goes straight to
   `python -m build` → `pypa/gh-action-pypi-publish` with **no** test run, **no**
   tag-vs-version check, **no** artifact audit, and **no** install smoke test.
   A broken, un-importable, or mismatched build becomes a permanent,
   un-yankable bad release on PyPI — the worst possible first impression for an
   OSS launch.
2. **Mutable action references.** Both `publish.yml` and `ci.yml` (and
   `install-test.yml`) pin `uses:` to moving tags (`@v4`, `@v5`,
   `@release/v1`). A compromised or retagged upstream action runs with our
   `id-token: write` trusted-publishing credential. Supply-chain pinning to
   immutable commit SHAs is table stakes for a project about to publish.
3. **The VS Code extension is never built or audited in CI.** `ci.yml` covers
   only the Python package. The TypeScript extension under `vscode-extension/`
   can break its compile, fail its tests, or pick up a high-severity npm
   advisory and ship unnoticed.

This change was flagged as a pre-launch task during the v5.19 audit
(scheduled, not yet specced). It is CI/release-process only — no application
source changes.

## What changes

- **`publish.yml` becomes a release gate.** Before the artifact reaches PyPI it
  must clear: the same quality bar as `main` (ruff check, ruff format --check,
  mypy src, full pytest, `pip-audit`), plus three release-only invariants —
  (a) the git tag equals the `pyproject.toml` version, (b) `twine check` passes
  on the built sdist+wheel, (c) the built wheel installs and runs (`halyard
  --version`) in a clean venv outside the source tree.
- **All `uses:` pinned to immutable commit SHAs** across `publish.yml`,
  `ci.yml`, and `install-test.yml`, with a trailing `# vX.Y.Z` comment for
  human review / Renovate.
- **New `vscode-extension` job in `ci.yml`:** `npm ci` → `npm run compile` →
  `npm test` (vitest) → `npm audit --audit-level=high`.

## Out of scope

- No application source changes.
- The publish gate runs on a single Python (3.12, the build/publish version),
  not the full 3.11–3.13 matrix — `ci.yml` already covers the matrix on every
  push to `main`; the release gate re-verifies the exact tagged tree once.

## Impact

- Affected: `.github/workflows/{publish,ci,install-test}.yml`, plus sdist
  hygiene (Finding 4): a one-line `.gitignore` addition keeping the local
  Hypothesis cache out of the sdist, and an explicit
  `[tool.hatch.build.targets.sdist]` include list in `pyproject.toml` so the
  release artifact ships the package, tests, and samples — not the whole repo.
- A mismatched or broken release now fails CI instead of landing on PyPI.
- The OSS supply-chain surface (action provenance, npm advisories) is gated.
