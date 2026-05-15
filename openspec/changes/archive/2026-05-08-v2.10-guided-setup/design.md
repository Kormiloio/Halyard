# v2.10 Guided Setup Design

## Command

```bash
halyard setup [--all] [--claude] [--cursor] [--gemini] [--yes] [--global-claude]
```

Default interactive behavior:

1. Check whether the current directory is a Halyard project.
2. Check whether a hub is configured.
3. Prompt for which supported hooks to install.
4. Install selected hooks by reusing existing installer functions.
5. Run a doctor-style summary.
6. Print a first-capture next step.

Non-interactive behavior:

- `--all --yes`: install all supported hooks without prompts.
- `--claude --yes`: install only Claude Code hooks.
- `--cursor --yes`: install only Cursor hooks.
- `--gemini --yes`: install only Gemini CLI hooks.
- multiple tool flags can be combined.

If no tool flags are provided and `--yes` is set, setup should default to
`--all`.

## Module Layout

```text
src/halyard/setup.py
tests/test_setup.py
```

`setup.py` should contain selection and summary logic. Hook writing remains in
the existing installer functions in `cli.py` for this slice, so behavior stays
consistent.

## Output

Text output should be short:

```text
Halyard Setup
Project: /path/to/project
Hub: not configured
Installing: Claude Code, Cursor, Gemini CLI
...
Next: run one AI session, then `halyard doctor --first-capture`
```

## Safety

- Existing installer idempotency remains the safety mechanism.
- Setup never deletes hook entries.
- Setup never edits prompts, transcripts, or source code.
- Setup does not create a project automatically in this slice; it tells users to
  run `halyard init`.

## Tests

Test command selection as pure logic, and CLI behavior with monkeypatched
installer functions. Do not write real user home files in tests.

