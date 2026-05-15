# Percent-Encode Free-Text Fields in `ai-sessions.log`

## Summary

Replace the current underscore-substitution scheme for `note`, `resume_command`,
`branch`, and other free-text key=value fields in `ai-sessions.log` with
percent-encoding (RFC 3986 unreserved set). This removes the ambiguity where
a legitimate underscore in user input is indistinguishable from a space that
was encoded.

## Motivation

The log format is space-delimited, so any free-text value containing a space
must be encoded. Today we substitute `_` for space, which has two problems:

1. **Ambiguity on read.** A user-supplied note containing `snake_case_name`
   cannot be distinguished from `snake case name` after encoding.
2. **Round-trip loss.** The encoded form is what's persisted; on parse we
   cannot recover the user's original intent.

Percent-encoding (`%20` for space, `%25` for `%`) is a well-understood,
reversible alternative. It's already what the URL and HTTP form-encoding
layers use, and Python has `urllib.parse.quote` / `unquote` built in.

## Scope

In:
- `_safe_field()` and the inverse decode in `AiSession.from_log_line()`.
- All fields that today pass through underscore substitution.
- Backward-compatible read path: existing logs with `_`-encoded values
  continue to parse correctly.

Out:
- Structured fields (timestamps, integers, model names with no spaces).
- The `s ` / `a ` line prefix and positional ordering.

## Acceptance

- New sessions written by the post-change code use percent-encoding.
- Old sessions written by the pre-change code still parse and amend
  correctly.
- A round-trip test fixture covers: space, underscore, percent sign,
  unicode codepoints in `note` and `resume_command`.
- `session_hash()` is stable for old lines (no rewrite of historical
  entries).

## Notes

This is a format evolution, not a breaking change — readers must handle
both schemes. The decision to migrate existing lines is a separate
follow-up.
