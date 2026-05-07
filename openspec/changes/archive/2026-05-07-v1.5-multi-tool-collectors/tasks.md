# Tasks

Implementation checklist for v1.5 — Multi-Tool Collectors and Ambient Capture.

## 1. Codex Desktop importer

- [x] 1.1 Implement `collectors/codex_app.py` — parse `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`;
       extract `session_meta`, `turn_context`, `event_msg(token_count)` events; compute
       net_input = input - cached; skip sessions with output_tokens == 0
- [x] 1.2 Implement `~/.halyard/codex-imported` deduplication state (UUID per line)
- [x] 1.3 Add `halyard import-codex [--dry-run] [--all]` CLI command
- [x] 1.4 Write `tests/test_codex_importer.py` — 16 tests covering parse, dedup,
       dry-run, hub fallback, cache tokens, project inference

## 2. Gemini CLI collector

- [x] 2.1 Implement `collectors/gemini_cli.py` — three entry points:
       `record_session_start()`, `record_model_usage()`, `handle_agent_stop()`
- [x] 2.2 State file `~/.halyard/gc-session` — JSON with turn_start, cwd, model,
       prompt_tokens, output_tokens, cache_tokens; reset on AfterAgent
- [x] 2.3 Cost calculation: `billing=api`, `calculate_cost(model, net_input, output_tokens,
       cache_read=cache_tokens)`, `cachedContentTokenCount` extraction
- [x] 2.4 Add hidden CLI commands: `gc-session`, `gc-model`, `gc-hook`
- [x] 2.5 Add `halyard install-gemini-hook` — writes three hook entries to
       `~/.gemini/settings.json` with absolute executable path
- [x] 2.6 Write `tests/test_gemini_collector.py` — full turn sequence, cache tokens,
       billing, state reset, hub fallback

## 3. Cursor collector

- [x] 3.1 Implement `collectors/cursor.py` — `record_session_start()` (idempotent) and
       `handle_stop_hook()`; workspace_roots-first project resolution
- [x] 3.2 `workspace_roots` is authoritative: if roots given but none match, return None
       (do not fall back to CWD — CWD is the terminal's, not the workspace's)
- [x] 3.3 Add hidden CLI commands: `cursor-session`, `cursor-hook`
- [x] 3.4 Add `halyard install-cursor-hook` — writes two hook entries to
       `~/.cursor/hooks.json` with absolute executable path
- [x] 3.5 Write `tests/test_cursor_collector.py` — 10 tests covering session start,
       stop, workspace resolution, token fields, billing

## 4. Duplicate suppression

- [x] 4.1 Add `cursor_version` guard in `claude_code.handle_stop_hook()` — detect
       Cursor-fired hooks and return early to prevent double-recording
- [x] 4.2 Write test: `test_stop_hook_skips_cursor_events` in `test_v1_collectors.py`

## 5. Ambient capture — hub

- [x] 5.1 Implement `hub.py` — `find_hub()`, `set_hub(path)`, `clear_hub()`
- [x] 5.2 All four collectors: replace bare `return 0` on no-project with
       `find_project_dir(start=cwd) or find_hub()`
- [x] 5.3 Add `--hub` flag to `halyard init` — designates initialized dir as hub
- [x] 5.4 Add `halyard hub [PATH]` command — show status or set hub
- [x] 5.5 Write `tests/test_hub.py` — 6 tests

## 6. Ambient capture — git inference

- [x] 6.1 Implement `git_context.py` — `infer_project(cwd)`, `current_branch(cwd)`,
       `current_remote(cwd)`, `register_repo(pattern, slug)`, URL normalization
- [x] 6.2 `~/.halyard/repos.toml` `[repos]` table — supports exact and `*` wildcard patterns
- [x] 6.3 All four collectors: set `project = active_timer or infer_project(cwd)`
- [x] 6.4 All four collectors: set `tags=[f"branch:{branch}"]` when on a named branch
- [x] 6.5 Add `halyard link-repo <slug>` CLI command — maps current repo's remote to slug
- [x] 6.6 Write `tests/test_git_context.py` — 16 tests covering normalization, matching,
       inference, branch, register

## 7. Absolute path in hook installers

- [x] 7.1 Add `_halyard_exe()` to `cli.py` — resolves absolute path of running binary
- [x] 7.2 All three install commands embed resolved path in hook configs so hooks
       fire correctly from tools' restricted shell environments

## 8. Quality

- [x] 8.1 All 175 tests passing
- [x] 8.2 `mypy src` clean (16 source files)
- [x] 8.3 `ruff check` and `ruff format` clean
