# Tasks — v5.12 Windows portability

- [x] Mechanical UTF-8 pass over `src/halyard/`: every text `read_text` /
      `write_text` / `open` gains `encoding="utf-8"`.
- [x] Same pass over `tests/`.
- [x] `jsonio` emits `Path.as_posix()` so a serialized path is cross-platform.
- [x] ruff: enable `PLW1514` and run `ruff check --fix` to catch any straggler.
- [x] Local: ruff + mypy + full pytest green (no regression on Linux).
- [x] Push; verify the `test-windows` CI job is green (or much smaller residue).
- [x] Iteration 2: address remaining Windows failures (Copilot importer,
      anything else surfaced).
- [x] Once green: flip `test-windows` to required (`continue-on-error: false`).
- [x] project.md roadmap entry; commit each iteration cleanly.
