# v3.5 — Claude Code client-surface tag: Tasks

Status: **shipped.**

## Phase 0 — read-only spike (blocks all of Phase 1+)

- [x] Author `tools/spike_claude_code_surface.py` (not committed):
  prints `os.environ` (allowlisted keys only — `CLAUDECODE*`,
  `CLAUDE_CODE_*`, `TERM_PROGRAM`, `__CFBundle*`, `TERM`, `SHELL`,
  `SSH_*`), `os.getppid()` + ancestry via `ps -o comm=`,
  `sys.stdin.isatty()`, and the Stop-hook `payload` keys.
- [x] Run it from a **terminal** Claude Code session → save dump.
- [x] Run it from a **desktop** Claude Code session → save dump.
- [x] Produce the signal-table in `design.md` "Detection rules"
  section; replace every "pending Phase-0" caveat with the confirmed
  signal name and value.
- [x] Decision: pick the minimal reliable subset for the cascade.

## Phase 1 — schema + detector

- [x] Add `client_surface: str | None = None` to `AiSession`
  ([src/halyard/ai_log.py:250](src/halyard/ai_log.py:250)).
- [x] Create `src/halyard/collectors/claude_code_surface.py` with
  `detect_surface() -> str | None`. Pure function, no I/O beyond
  env reads and at most one `ps` subprocess call (gated behind a
  short timeout).
- [x] Wire the call into `handle_stop_hook()`
  ([src/halyard/collectors/claude_code.py:120](src/halyard/collectors/claude_code.py:120))
  immediately before `AiSession(...)` construction.
- [x] Confirm log round-trip works without serializer changes
  (existing key=value contract).

## Phase 2 — tests

- [x] `tests/test_v35_claude_code_surface.py` covering cases 1–8 in
  `design.md` "Tests" section.
- [x] Regression: every existing `claude-code` collector test still
  passes unmodified — `client_surface` is purely additive.
- [x] v2.59 drift canary entry for `client_surface` regressing from
  populated to `None`.

## Phase 3 — surfacing

- [x] Dashboard: optional sub-row under `claude-code` when ≥1
  session in the window has a populated `client_surface`.
  Label: "client surface (heuristic)".
- [x] TUI: add `client_surface` to the per-session detail panel.
- [x] `halyard report --by-surface` flag; default output unchanged.
- [x] Web JSON (v2.69): include field only when populated.

## Phase 4 — docs

- [x] Roadmap entry in `openspec/project.md` (item 58, after v3.4).
- [x] PRD §reporting note: new optional column, advisory tag.
- [x] README quickstart: one-line mention that Claude Code sessions
  now break down by client surface where detectable.

## Gate

- [x] `pytest` green (target: +8 tests over baseline)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] Phase-0 spike dump archived locally (not committed) so the
  detection rules in `design.md` are reproducible.
