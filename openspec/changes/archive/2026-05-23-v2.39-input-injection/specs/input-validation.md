# Spec — Untrusted input validation

## Requirement: Business name cannot inject TOML

WHEN `halyard init` derives the business name from `git config user.name`
THEN the value MUST be sanitized (control chars, `"`, and `\` removed,
length-capped) before being written to `halyard.toml`
AND the rendered file MUST be re-parsed; if it does not parse or
`[business].name` differs from the sanitized value, the safe default
MUST be used.
SO THAT a malicious repo-local `user.name` cannot inject TOML keys.

## Requirement: Transcript path is validated before read

WHEN a Claude Code hook payload supplies `transcript_path`
THEN it MUST be ignored unless it resolves to a regular file, is not a
symlink, lies under an allowlisted root (the user's home, the system
temp dir, or the current working directory), and is no larger than
25 MB
AND the file MUST be read incrementally (not fully materialized).
WHEN the path fails any check
THEN transcript enrichment is skipped and the hook still completes
successfully.

## Requirement: External history reads are size-bounded

WHEN Halyard reads a Gemini history JSON file
THEN files larger than 25 MB MUST be skipped (treated as absent)
rather than read into memory.

## Requirement: Audit tolerates malformed commit diffs

WHEN `rate_history_from_git` encounters a `+rate=`/`+hourly_rate=` line
whose value is not a valid float
THEN that line MUST be skipped and the audit MUST continue, never raising.
