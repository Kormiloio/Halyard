# v2.51 — MCP Auto-Registration: Tasks

- [x] `cli_hooks.py`: `_MCP_SERVER_NAME`, `_mcp_entry`,
  `_MCP_CLIENTS`, `_do_install_mcp(client)` (reuse shared helpers,
  no-clobber, idempotent, foreign-preserving)
- [x] `cli_hooks.py`: `_auto_install_detected_mcp()` (PATH-gated,
  best-effort OSError) + register `install-mcp-claude|cursor|gemini`
  and hidden `install-mcp`
- [x] `cli_setup.py`: call `_auto_install_detected_mcp()` in `init`
  after hooks; register MCP per selected tool in `setup`
- [x] README: replace manual MCP snippet with auto-register note
- [x] Tests: `tests/test_v251_mcp_autoregister.py` (9 cases)

## Gate
- [x] `pytest` green (1077 passing)
- [x] `ruff check` + `ruff format --check` clean
- [x] `mypy src/` clean
- [x] roadmap entry + status in `openspec/project.md`
