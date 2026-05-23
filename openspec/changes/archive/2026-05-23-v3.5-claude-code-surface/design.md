# v3.5 — Claude Code client-surface tag: Design

The design for advisory client-surface detection, confirmed by Phase-0
spike results.

## Where

- **New module:** `src/halyard/collectors/claude_code_surface.py` —
  a single pure function `detect_surface() -> str | None` returning
  `"cli" | "desktop" | "ide" | "unknown" | None`. Isolated module so
  the heuristic stays testable and swappable when upstream offers a
  real signal.
- **Call site:** `handle_stop_hook()` in
  [src/halyard/collectors/claude_code.py:237](src/halyard/collectors/claude_code.py:237),
  one call right before constructing `AiSession`. The value is passed
  into the dataclass as `client_surface`.
- **Schema:** one new optional field on `AiSession`
  ([src/halyard/ai_log.py:291](src/halyard/ai_log.py:291)) —
  `client_surface: str | None = None`. Serialisation is automatic via
  the existing key=value contract; no parser change beyond the field
  declaration.
- **Reports / dashboard / TUI:** sub-bucket on the existing
  `tool="claude-code"` row. Same pattern as `mcp_server_names` in
  v3.4 — additive column when data exists, silent when it doesn't.

## Detection rules

The detector is a short ordered cascade. First match wins; if none
match, return `None` (or `"unknown"` — see Open question below).

```
1. If __CFBundleIdentifier env var indicates Anthropic's desktop
   bundle (startswith "com.anthropic.claude" or "com.anthropic.Claude")
   → "desktop".
2. If TERM_PROGRAM is "vscode" → "ide".
3. If TERM_PROGRAM is a real terminal emulator (iTerm.app,
   Apple_Terminal, WezTerm, Alacritty, kitty, tmux, screen, etc.)
   and the parent-process chain does NOT include "claude" or
   "anthropic" markers → "cli".
4. If stdin is a TTY → "cli".
5. Otherwise → "unknown" (the explicit string), so dashboards can
   show the bucket honestly rather than blank.
```

The parent-process chain walk is a last-resort to distinguish a
terminal launched *by* the desktop app (which inherits terminal-like
env vars) from a standalone terminal.

## Semantics

- **Advisory tag, honestly labelled.** Anywhere the field is
  rendered (dashboard, TUI, report), the column header or tooltip
  reads "client surface (heuristic)" — same convention as the v2.32
  trust-labelling for inferred attribution.
- **Unavailable is not zero.** If detection cannot reach a decision,
  the field is `None` (not silently `"cli"`). v2.59 drift canary
  ensures that if a surface that *was* being detected stops being
  detectable, we surface a regression rather than degrade silently.
- **No raw env in the log.** The detector reads env vars locally and
  writes only the bucketed string. Raw values never leave the
  function.
- **Single source of truth.** No other module calls into
  `detect_surface()`; `handle_stop_hook` writes the value, every
  downstream consumer reads it off `AiSession`.

## Reporting

- **Dashboard:** `claude-code` row gains an optional breakdown — same
  visual treatment as v3.4 MCP server names. Hidden when every session
  in the window has `client_surface=None`.
- **TUI:** add `client_surface` to the per-session detail panel; no
  new top-level view.
- **`halyard report`:** opt-in `--by-surface` flag that groups the
  `claude-code` rows by `client_surface`; default output unchanged so
  existing scripts/pipelines see no diff.
- **Web JSON output (v2.69):** field appears in session JSON if
  populated; absent (not `null`-emitted) otherwise to keep the
  contract minimal.

## Tests (`tests/test_v35_claude_code_surface.py`)

All driven through `monkeypatch` on `os.environ` and
`os.getppid`/`psutil` (whichever the detector chose). No real process
spawning, no real `.app` bundle — pure unit tests.

1. CLI shape: terminal env vars present, no bundle id → `"cli"`.
2. Desktop shape: bundle id present → `"desktop"` even if
   `TERM_PROGRAM` is also set (desktop wins over a wrapping pty).
3. IDE shape: `TERM_PROGRAM=vscode` and no bundle id → `"ide"`.
4. Ambiguous shape: no recognisable signal → `"unknown"` (or `None`
   per the Open question).
5. Round-trip: an `AiSession` with `client_surface="cli"` writes a log
   line that parses back to the same value.
6. Old log line (no `client_surface=` token) parses to
   `client_surface=None` — no migration, no warning.
7. v2.59 drift canary: if the detector regresses from `"cli"`/`"desktop"`
   back to `None` for an identical environment, the canary fires.
8. Privacy: the detector function, given a `MONEY_SECRET=foo`
   environment, never references that key and never writes it to
   stdout, stderr, or any log path.

## Open questions

- **`"unknown"` vs. `None`?** Two ways to say "we don't know":
  serialise `client_surface="unknown"` (visible in reports as its
  own bucket) or leave it `None` (suppressed). Recommend
  `"unknown"` for live sessions where the hook *ran* but signals
  were ambiguous, and `None` for older log lines from before v3.5.
  This makes the report show "we tried and couldn't tell" distinct
  from "we never tried".
- **IDE detection scope.** If Phase-0 shows VS Code / JetBrains
  signals are present and free, ship `"ide"` as a third bucket. If
  detection would need separate spikes per IDE, defer.
- **Web app (claude.ai/code).** Out of scope — that surface does not
  trigger local hooks. Documented as N/A.

## Gate

`pytest` + `ruff check` + `ruff format --check` + `mypy src/`.
Roadmap entry in `openspec/project.md` (item 58 — placement after
v3.4). PRD/ARD touch-up only if behaviour-visible to end users
(adds a column → yes; touch PRD §reporting).
