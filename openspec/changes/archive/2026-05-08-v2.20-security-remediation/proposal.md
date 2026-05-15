# Proposal: v2.20 — Security Remediation

## Why this change

A targeted vulnerability scan by Adrian identified 11 security findings in
the existing codebase: 2 High, 5 Medium, and 4 Low severity. The findings
covered cross-origin request forgery exposure, an unvalidated URL injection
path for the OpenAI base URL, log injection via hook payloads, path traversal
in invoice generation, and several smaller hardening gaps.

These are surgical correctness issues in the existing code, not new
architectural requirements. The right response is targeted fixes — not a
redesign.

## What this change does

Kai applied surgical fixes for all 11 findings:

- **H-1:** Origin header validation on dashboard POST endpoints — cross-origin
  requests from non-localhost origins return 403.
- **H-2:** `openai_base_url` is validated before any OpenAI client is
  constructed; non-HTTPS, non-localhost URLs (including `file://`, `data://`,
  arbitrary HTTP) raise `LogAgentError`.
- **M-1:** Hook payload sanitization — `tool` and `model` values with embedded
  whitespace or `=` characters have those replaced with `_` before being
  written to the session log.
- **M-2:** The encoding contract for `note` and `resume_command` (spaces →
  underscores, newlines stripped, known round-trip ambiguity with literal
  underscores) is documented in `ai_log.py`.
- **M-3:** Slug validation for `clients.toml` and `projects.toml` — records
  whose slug does not match `^[a-z0-9][a-z0-9-]{0,63}$` are skipped before
  any invoice path is constructed from them.
- **M-4:** Invoice path traversal guard — paths that resolve outside the
  project's `invoices/` directory raise `InvoiceError` before any file write
  or subprocess call.
- **M-5:** Quarantine log newline sanitization — newlines in error strings
  passed to `_write_quarantine()` are replaced with spaces.
- **L-1:** Jinja2 `autoescape=False` is documented with an inline comment
  explaining the intentional choice for Markdown output.
- **L-2:** `launchctl unload` non-zero exit handling — a warning is printed to
  stderr; the plist is still removed regardless.
- **L-3:** Atomic writes in attribution functions — `assign_unattributed_sessions()`,
  `confirm_session_attributions()`, and `backfill_window()` all use
  tmp-then-rename.
- **L-4:** `pip-audit` added to CI and to `[dev]` extras in `pyproject.toml`.
- **L-5:** `halyard init` writes `.halyard/` to the generated `.gitignore`.

## What this change does NOT do

- No API changes. All existing CLI commands and their arguments are unchanged.
- No log format changes (M-2 documents the existing encoding; it does not alter
  it).
- No new dependencies. All fixes use the standard library or already-present
  packages.

## Key decisions

**Why surgical fixes rather than architectural changes?**

Adrian's scan identified concrete, exploitable paths. Surgical fixes close
those paths immediately with minimal blast radius. Broader architectural
questions (e.g., full token-based dashboard auth, amendment-record log
rewriting) remain on the roadmap in their own change specs and are not
conflated here.

**Why document M-2 rather than fix it?**

The spaces-to-underscores encoding in `note` and `resume_command` has a known
round-trip ambiguity: a literal underscore in the original value is
indistinguishable from an encoded space after a round-trip. Changing the
encoding would alter existing log lines. The correct path is documentation now
and a deliberate migration spec later if the ambiguity proves harmful in
practice.

## Success criteria

- All 11 findings have corresponding tests.
- 39 new tests added, all passing.
- ruff and mypy report no new errors.
- No existing test regressions.
