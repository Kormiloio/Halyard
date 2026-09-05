# v5.30 — Design

## Why the extras join the existing job, not a new one

The tempting shape is a dedicated `audit` job: install everything once,
audit once, keep the test environment untouched. It was rejected because the
audit is **not** version-independent, and this repo already has the scar to
prove it.

v5.29's companion CI fix existed because `setuptools 79.0.1` shipped on the
3.11 runner image and not on 3.12/3.13 — a single matrix leg was red. A
consolidated audit job would run on one interpreter and miss exactly that
class of finding. Resolution differs per Python version, so the audit
belongs in the matrix.

The remaining objection is that installing `[all]` perturbs the test run —
tests that currently skip on a missing `mcp` would begin executing. That was
checked rather than assumed: the development venv already carries
`--all-extras`, and the suite is green there, so the extras change coverage
upward without changing outcomes.

## Why the `mcp` upper bound is not "pin hygiene"

Upper bounds on libraries are usually a smell — they cause resolution
conflicts downstream and age badly. This one is load-bearing.

`mcp_server.py:205` imports `mcp.server.fastmcp.FastMCP`. In mcp 2.x that
module does not exist; the class is `mcp.server.mcpserver.MCPServer`. There
is no compatibility shim. So `mcp>=1.2` does not express "any mcp" — it
expresses "any mcp, and please crash on the ones after 1.x".

The alternative is to support both majors behind a try/except import. That is
a genuine option and a better long-term answer, but it is a feature (new API
surface, new tests, new failure modes) and does not belong in a change whose
purpose is closing an audit gap. The pin is the honest description of what
the code supports today.

The lower bound (`>=1.28.1`) is chosen over `>=1.27.2` because
PYSEC-2026-3483 is only fixed in 1.28.1; the other two mcp advisories are
fixed in 1.27.2. Taking the higher floor clears all three with one bound.

## Why the error message change is in scope

It is the reason the defect survived. A wrong-major SDK and an absent SDK
both raise `ModuleNotFoundError`, and collapsing them into one message
produces advice that actively reinforces the mistake: reinstall the extra →
resolve 2.x again → identical error. That is the same failure shape as
v5.29's stale hub pointer, where `find_hub()` collapsed "unconfigured" and
"vanished" into `None` and the doctor printed a confidently wrong diagnosis.

The fix distinguishes them with `importlib.util.find_spec("mcp")` — is the
top-level package importable at all? — and prints the original exception
text when it is. Upstream's message already names the rename, links the
migration guide, and suggests `mcp<2`; swallowing it was the whole problem.

## Verification

Inspection is insufficient here: the question is what a resolver does today,
which no amount of reading the manifest answers. Each claim was checked
against a real environment.

A 3.11 venv built the way CI builds one (`pip install --upgrade pip
setuptools`, then `pip install -e ".[dev,all]"`):

- resolves `setuptools 84.0.0`, confirming v5.29's companion fix clears the
  83.0.0 floor on the leg that was actually red — previously argued from
  PyPI metadata alone
- resolved `mcp 2.1.1` **before** the pin, and `halyard mcp` failed to start
- resolves `mcp 1.29.1` after, and `halyard mcp` answers a real `initialize`
  request with a protocol response
- audits clean: `No known vulnerabilities found`

Note the earlier reading of `setuptools 82.0.1` from a system Python 3.9 venv
was a Python-version cap, not a counter-example — another instance of the
per-version resolution difference that keeps the audit inside the matrix.

The CI-shape assertion is a string match on `ci.yml` rather than a mock. It
is crude, but the alternative is no coverage at all: the failure being
guarded against is someone reverting the install line, and a test that reads
the workflow catches exactly that.
