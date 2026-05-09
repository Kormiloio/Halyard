# Spec: v2.22 — Security Architecture

## Overview

Three design-level security findings from Sage's architectural review (D-3,
D-4, D-5), plus 10 test coverage gaps identified in the same review. None
of the D-3/D-4/D-5 findings are yet implemented.

---

## D-4: Plist XML injection

### WHEN service.py constructs the launchd plist
THEN project_dir and any other interpolated strings are escaped with
xml.sax.saxutils.escape() before insertion into the plist XML template.

### WHEN project_dir contains < > or & characters
THEN the generated plist is valid XML (verified by an XML parser).

### WHEN project_dir contains no XML-special characters
THEN the generated plist is identical to what would have been generated
without escaping.

---

## D-3: org.toml change detection

### WHEN org.toml is loaded at startup
THEN a SHA-256 hash of the file content is computed.

### WHEN the computed hash differs from the hash stored in ~/.halyard/org-hash.txt
THEN a warning is printed to stderr:
"[halyard] Warning: org.toml has changed since last run. Historical sessions
may be re-attributed on next sync."
The new hash is stored in ~/.halyard/org-hash.txt after the warning.

### WHEN the computed hash matches ~/.halyard/org-hash.txt
THEN no warning is printed. The file is loaded normally.

### WHEN ~/.halyard/org-hash.txt does not exist (first run)
THEN no warning is printed. The hash is computed and stored for future runs.

---

## D-5: Pricing table hash pinning

### WHEN the remote pricing table is fetched
THEN the response body is hashed with SHA-256 and compared against the hash
stored in ~/.halyard/pricing-hash.txt.

### WHEN the hashes differ (or pricing-hash.txt does not exist)
THEN a warning is printed before the new table is accepted:
"[halyard] Warning: remote pricing table has changed. Review before accepting."
The new hash is NOT written to pricing-hash.txt until the table is explicitly
accepted.

### WHEN the hashes match
THEN the pricing table is accepted silently. No warning is printed.

### WHEN the remote fetch returns a truncated or incomplete response
THEN the local pricing table is not overwritten and the stored hash is not
updated.

---

## Test coverage gaps

### Gap 1: Session round-trip fidelity
WHEN an AiSession is written via to_log_line() and parsed via from_log_line()
THEN all fields on the parsed session are identical to the original session.

### Gap 2: Active file concurrent-write simulation
WHEN two writes to ~/.halyard/active are in flight simultaneously
THEN a concurrent read always returns either the previous complete slug or the
new complete slug — never a partial or corrupted slug.

### Gap 3: Partial active file read
WHEN ~/.halyard/active contains a truncated write (incomplete slug)
THEN read_active_project() returns None rather than a malformed slug.

### Gap 4: org.toml change detection
WHEN org.toml content changes between two runs
THEN a warning is produced on the second run.
WHEN org.toml content is unchanged between two runs
THEN no warning is produced.

### Gap 5: Attribution cascade priority
WHEN both an active timer and a git inference are available at session end
THEN attr_method=timer is used and attr_method=git is not.

### Gap 6: Plist XML injection
WHEN project_dir contains < > & characters
THEN the generated plist is parseable by an XML parser without error.

### Gap 7: Gemini session-id 8-char prefix collision
WHEN two Gemini sessions share the same 8-character session-id prefix
THEN each session is attributed independently and neither overwrites the
other's attribution.

### Gap 8: Pricing table partial-fetch
WHEN the remote pricing table HTTP response is truncated before completion
THEN the local pricing table file is not overwritten.
THEN the stored hash in pricing-hash.txt is not updated.

### Gap 9: read_sessions tool limit parameter
WHEN read_sessions is called with a very large limit value
THEN the function completes within an acceptable time bound and does not
cause out-of-memory errors.

### Gap 10: _validate_base_url with localhost variants
WHEN openai_base_url is set to http://127.0.0.1
THEN the URL is accepted.
WHEN openai_base_url is set to http://localhost
THEN the URL is accepted.
WHEN openai_base_url is set to http://[::1]
THEN the URL is accepted.
WHEN openai_base_url is set to http://127.0.0.1:8080 or http://localhost:11434
THEN the URL is accepted (port variants pass validation).
WHEN openai_base_url is set to http://192.168.1.1
THEN the URL is rejected with LogAgentError.
