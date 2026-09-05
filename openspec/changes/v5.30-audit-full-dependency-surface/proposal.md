# v5.30 — CI audits only half the dependency surface

## Why

`halyard doctor`-adjacent CI reported the dependency audit green while **27
advisories** sat open against the packages behind the Hub's network-facing
code. The audit never saw them.

`lint-and-test` installs `pip install -e ".[dev]"`, and `pip-audit
--skip-editable` inspects the installed environment in place. The `[dev]`
group is pytest, ruff, mypy, hypothesis, pip-audit, freezegun. The `mcp`
extra — and everything under it — is never installed, so it is never
audited:

```
cryptography      48.0.0   PYSEC-2026-3553, PYSEC-2026-3554, GHSA-537c-gmf6-5ccf
mcp               1.27.1   PYSEC-2026-3481, PYSEC-2026-3482, PYSEC-2026-3483
starlette         1.0.0    PYSEC-2026-161, -248, -249, -2280, -2281
pyjwt             2.12.1   PYSEC-2026-175 … -179
python-multipart  0.0.28   PYSEC-2026-3036, -3037, -3040
msgpack           1.1.2    PYSEC-2026-3625
pydantic-settings 2.14.1   GHSA-4xgf-cpjx-pc3j
```

That is the transport, auth, and crypto stack for the Hub — the component
that opens a socket. GitHub's Dependabot could see them (it reads the
manifest); the gate meant to catch them could not.

This matters now because roadmap item 2 gates the OSS launch on
`pipx install halyard && halyard init` working end-to-end. Going public with
an unaudited socket-facing dependency surface is the wrong first impression.

## The second defect, found while fixing the first

Installing `[all]` in CI turned out to be unsafe as the manifest stood.

`mcp = ["mcp>=1.2"]` admits **mcp 2.x**, where FastMCP was renamed to
MCPServer. `mcp_server.py:205` imports `mcp.server.fastmcp`, which does not
exist there:

```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'. This is mcp 2.x,
where FastMCP was renamed to MCPServer …
```

A fresh `pip install -e ".[dev,all]"` on 3.11 resolves **mcp 2.1.1** today, so
adding the extra to CI would have installed a server that dies on startup —
and nothing would have gone red. The full suite passes with mcp 2.x present
(1769 passed): no test calls `build_server()`, so the failure is invisible to
CI, to the audit, and to the test suite simultaneously.

Worse, `cli_mcp.py` catches that `ModuleNotFoundError` and prints:

> Error: the MCP SDK is not installed. Install it with: `pip install 'halyard[mcp]'`

The SDK *is* installed; it is the wrong major version. The advice sends the
user to reinstall an extra they already have — and the reinstall resolves 2.x
again, reproducing the identical message. This misdiagnosis is not
hypothetical: it cost a wrong conclusion during this very investigation, and
the same message is what the maintainer's `halyard` MCP server has been
emitting all session.

## What

1. **`pip install -e ".[dev,all]"`** in `lint-and-test`, so the audit covers
   the optional surface. The clean no-extras install path stays covered by
   `install-test.yml`, which builds and smoke-tests a bare wheel.
2. **`mcp>=1.28.1,<2`** in both the `mcp` and `all` extras. The lower bound
   clears PYSEC-2026-3481/3482/3483; the upper bound is load-bearing, not
   hygiene — it is the difference between a working server and one that dies
   on import.
3. **`uv lock --upgrade`**, clearing all 27 advisories for local development.
4. **Separate the two `cli_mcp` failure modes** — "not installed" vs
   "installed but incompatible" — and surface the underlying import error,
   which upstream writes well enough to act on.

Verified empirically rather than by inspection: a 3.11 venv built the way CI
builds one now audits clean (`No known vulnerabilities found`), the full
suite passes against the upgraded pins, and `halyard mcp` answers a real
`initialize` request.

## Out of scope

- **Making CI resolve through `uv.lock`.** CI uses `pip install`, which
  re-resolves from PyPI within the pyproject ranges and ignores the lock
  entirely. So the lock and CI can diverge: a stale lock leaves local
  development vulnerable while CI stays green, which is exactly what
  happened here. Closing that means switching CI to `uv sync --locked` — a
  real improvement, and a bigger change than this one.
- Auditing the `openai` extra's surface separately; it comes along with
  `[all]` and is covered incidentally.
- The 9 open Dependabot PRs. None of them touch these packages — they are
  Actions pins and dev-tooling ranges. The advisories here had no Dependabot
  PR because the fixed versions already satisfied the pyproject ranges; it
  was `uv.lock` that was stale, and Dependabot's pip support does not write
  `uv.lock`.
