# Tasks — v5.12 Windows portability

- [ ] Mechanical UTF-8 pass over `src/halyard/`: every text `read_text` /
      `write_text` / `open` gains `encoding="utf-8"`.
- [ ] Same pass over `tests/`.
- [ ] `jsonio` emits `Path.as_posix()` so a serialized path is cross-platform.
- [ ] ruff: enable `PLW1514` and run `ruff check --fix` to catch any straggler.
- [ ] Local: ruff + mypy + full pytest green (no regression on Linux).
- [ ] Push; verify the `test-windows` CI job is green (or much smaller residue).
- [ ] Iteration 2: address remaining Windows failures (Copilot importer,
      anything else surfaced).
- [ ] Once green: flip `test-windows` to required (`continue-on-error: false`).
- [ ] project.md roadmap entry; commit each iteration cleanly.
