# v2.39 — Input Injection Hardening: Design

## #1 — TOML injection in `halyard init`

`_HALYARD_TOML_TEMPLATE` is kept (it carries more than the business
name), but `business_name` is sanitized before `.format()`:

- strip control characters (incl. CR/LF/tab),
- drop `"` and `\` (the two characters that can break out of a
  double-quoted TOML basic string),
- collapse internal whitespace, cap at 80 chars,
- fall back to `"Your Name Consulting"` if nothing usable remains.

A defensive round-trip check is added: after formatting, the result is
parsed with `tomllib`; if it does not parse or `[business].name` does not
equal the sanitized value, the safe default is used. This guarantees a
malformed `user.name` can never inject keys regardless of the sanitizer's
completeness. Sanitizer lives next to `_detect_business_name`.

## #2 — `transcript_path` validation

A new `_safe_transcript_path(raw: str) -> Path | None` in
`claude_code.py`:

- returns `None` for empty/non-str,
- `Path(raw).expanduser()` then `.resolve()`,
- reject if not `is_file()` (blocks dirs, FIFOs, devices, missing),
- reject symlinks (`os.path.islink` on the pre-resolve path),
- reject if not under an allowlisted root: `Path.home()`, the system
  temp dir, or `Path.cwd()` (Claude Code writes transcripts under
  `~/.claude/...`; tests/some setups use temp or the project tree). This
  blocks `/etc`, `/proc`, `/sys`, `/dev`, and other users' files while
  not breaking any real layout — a strict "under $HOME" rule rejected
  legitimate temp-dir transcripts,
- reject if `stat().st_size` exceeds `_MAX_TRANSCRIPT_BYTES` (25 MB).

The read is changed from `read_text().splitlines()` to a line-by-line
file iteration so a large (but in-policy) file is not fully materialized.
`None` → the enrichment is skipped (same as today's "no transcript"
path); the hook still succeeds.

Rationale for "under home": transcripts are tool-written user data;
restricting to `$HOME` blocks `/etc/*`, `/proc/*`, `/dev/*`, and other
users' files while not breaking any real Claude Code layout. This is a
deliberate, documented trust boundary, not a guess.

## #3 — Gemini history size cap

`gemini_history` reads are guarded by a shared `_MAX_HISTORY_BYTES`
(25 MB) `stat`-then-skip check before `read_text()`. Oversized files are
treated as "no history" (return None), consistent with the existing
unreadable-file handling.

## #4 — `config_history` float guard

The two `float(m.group(1))` calls in `rate_history_from_git` are wrapped
so a non-numeric capture (`1.2.3`) is skipped (`continue`) instead of
raising, matching the file's existing defensive style.

## Test strategy

Each fix gets a regression test in
`tests/test_v239_input_injection.py`:

- `user.name` containing `"` + newline + injected key → resulting
  `halyard.toml` parses and contains no injected key.
- `transcript_path` = `/etc/passwd`, a symlink, a path outside home, and
  an oversized file → all skipped, hook still returns a session.
- oversized Gemini history file → import skips it without OOM.
- crafted `git log` diff with `+rate = 1.2.3` → audit returns, no raise.

Full `pytest` + `ruff` + `ruff format --check` + `mypy` before commit.
