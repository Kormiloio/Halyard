# Spec: v2.20 — Security Fixes

## Overview

Eleven targeted fixes for findings from Adrian's vulnerability scan. Each
scenario maps to a finding ID (H = High, M = Medium, L = Low).

---

## H-1: Origin header validation

### WHEN a POST to /api/start or /api/stop carries an Origin header that is not 127.0.0.1 or localhost on the bound port
THEN the server returns 403 FORBIDDEN and does not process the request body.

### WHEN a POST to /api/start or /api/stop carries no Origin header
THEN the request is processed normally (absence of Origin is not treated as
cross-origin).

### WHEN a POST to /api/start or /api/stop carries an Origin header matching 127.0.0.1 or localhost on the bound port
THEN the request is processed normally.

---

## H-2: OpenAI base URL validation

### WHEN openai_base_url is set to a non-HTTPS URL that is not a localhost address (including file://, data://, or arbitrary HTTP)
THEN LogAgentError is raised before any OpenAI client is constructed.

### WHEN openai_base_url is set to an HTTPS URL
THEN the OpenAI client is constructed normally.

### WHEN openai_base_url is set to a localhost URL (127.0.0.1, localhost, ::1) regardless of scheme
THEN the OpenAI client is constructed normally (localhost URLs are trusted for
local dev use).

### WHEN openai_base_url is not set
THEN the default OpenAI endpoint is used; no validation is performed.

---

## M-1: Hook payload sanitization

### WHEN a hook payload contains a tool or model value with embedded whitespace or = characters
THEN those characters are replaced with _ before writing to the session log.

### WHEN a hook payload contains a tool or model value with no whitespace or = characters
THEN the value is written to the session log unchanged.

---

## M-2: note and resume_command encoding documentation

### The encoding contract for note and resume_command is documented in ai_log.py
The contract is: spaces are replaced with underscores, newlines are stripped
before writing. There is a known round-trip ambiguity: a literal underscore in
the original value is indistinguishable from an encoded space after parsing.
This ambiguity is documented; no encoding change is made in this release.

---

## M-3: Slug validation for config records

### WHEN clients.toml or projects.toml contains a slug that does not match ^[a-z0-9][a-z0-9-]{0,63}$
THEN that record is skipped with a warning and no invoice path is constructed
from it.

### WHEN clients.toml or projects.toml contains a slug that matches ^[a-z0-9][a-z0-9-]{0,63}$
THEN the record is loaded normally.

---

## M-4: Invoice path traversal guard

### WHEN an invoice path resolves outside the project's invoices/ directory
THEN InvoiceError is raised before any file write or subprocess call.

### WHEN an invoice path resolves inside the project's invoices/ directory
THEN the write or subprocess call proceeds normally.

---

## M-5: Quarantine log newline sanitization

### WHEN _write_quarantine() is called with an error string containing newlines
THEN the newlines are replaced with spaces before writing to quarantine.log.

### WHEN _write_quarantine() is called with an error string containing no newlines
THEN the error string is written unchanged.

---

## L-1: Jinja2 autoescape documentation

### The Jinja2 Environment uses autoescape=False
A comment in the source explains this is intentional: Halyard renders Markdown
templates, not HTML, and autoescaping would corrupt Markdown syntax.

---

## L-2: launchctl unload exit code handling

### WHEN launchctl unload exits with a non-zero code
THEN a warning is printed to stderr indicating the exit code and the plist
file path. The plist file is still removed regardless of the exit code.

### WHEN launchctl unload exits with code 0
THEN the plist file is removed and no warning is printed.

---

## L-3: Atomic writes in attribution functions

### WHEN assign_unattributed_sessions() rewrites the unattributed log
THEN the write uses a tmp-then-rename pattern so readers never observe a
partial file.

### WHEN confirm_session_attributions() rewrites any log file
THEN the write uses a tmp-then-rename pattern.

### WHEN backfill_window() rewrites any log file
THEN the write uses a tmp-then-rename pattern.

---

## L-4: pip-audit in CI

### pip-audit runs in CI after tests pass
pip-audit is listed in [dev] extras in pyproject.toml so it is available in
the development environment.

---

## L-5: .gitignore includes .halyard/

### WHEN halyard init generates a .gitignore for a new project directory
THEN .halyard/ is included in the generated .gitignore so per-user agent
state is not accidentally committed.
