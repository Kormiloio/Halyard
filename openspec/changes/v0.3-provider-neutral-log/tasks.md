# Tasks: v0.3 — Provider-Neutral `halyard log`

## Spec & design
- [x] Write proposal.md
- [x] Write specs/provider-neutral-log.md
- [x] Write design.md (tool schema sharing strategy, config loader, provider factory)

## `pyproject.toml` — optional extras
- [x] Add `openai = ["openai>=1.0"]` to `[project.optional-dependencies]`
- [x] Add `all = ["textual>=0.60", "openai>=1.0"]` convenience extra

## `src/halyard/log_config.py` (new module)
- [x] Define `LogConfig` dataclass:
  `default_agent`, `openai_base_url`, `openai_model`, `claude_model`
- [x] Implement `load_log_config() -> LogConfig`
  - Reads `~/.halyard/config.toml` if it exists
  - Returns defaults if file absent or key missing
  - Warns and uses default for unrecognised `default_agent` values
- [x] `_LOG_CONFIG_FILE = Path.home() / ".halyard" / "config.toml"`

## `src/halyard/log_agent.py` — OpenAI provider

### Shared tool schemas
- [x] Extract `_TOOLS` list to a shared constant usable by both providers
- [x] Verify Anthropic and OpenAI tool schema formats are compatible
  (they differ slightly in field names — adapt OpenAI via `_tools_for_openai()`)

### OpenAI provider
- [x] Implement `run_openai_log_query(query, project_dir, model, base_url, now) -> LogQueryResponse`
  - Import guard: catch `ImportError` on `import openai`, raise `LogAgentError` with install message
  - API key handling: require `OPENAI_API_KEY` only when `base_url` is the default OpenAI endpoint
  - Multi-turn tool-use loop using `openai.OpenAI(base_url=base_url).chat.completions.create()`
  - Tool dispatch: same `_dispatch_tool()` function as Claude provider
  - Normalise response into `LogQueryResponse` with `agent="openai"`
  - Handle `openai.BadRequestError` for models that don't support function calling

### Provider factory
- [x] Add `run_log_query(query, project_dir, agent, model, base_url, now) -> LogQueryResponse`
  - Dispatches to `run_local_log_query`, `run_claude_log_query`, or `run_openai_log_query`
  - `agent` defaults to `load_log_config().default_agent`
  - `model` and `base_url` fall back to config values when not explicitly passed

## `src/halyard/cli.py` — update `halyard log`
- [x] Add `--base-url` option to `log` command
- [x] Pass `base_url` to `run_log_query()`
- [x] Config loading: call `load_log_config()` for defaults when flags not set
- [x] Update help text to mention `--agent openai` and Ollama example

## Tests (`tests/test_log_config.py`)
- [x] `test_load_log_config_absent_file` — returns all defaults
- [x] `test_load_log_config_valid` — reads agent, base_url, model from file
- [x] `test_load_log_config_unknown_agent_warns` — prints warning, returns local default
- [x] `test_load_log_config_cli_overrides_file` — CLI `--agent` beats config value

## Tests (`tests/test_log_agent_openai.py`)
- [x] `test_run_openai_log_query_no_package` — mock ImportError, raises LogAgentError
- [x] `test_run_openai_log_query_no_api_key` — default base URL, no key → LogAgentError
- [x] `test_run_openai_log_query_local_no_key_required` — local base URL, no key → proceeds
- [x] `test_run_openai_log_query_success` — mock openai SDK, verify tool dispatch and response
- [x] `test_run_openai_log_query_no_tool_support` — BadRequestError → LogAgentError with message

## Quality
- [x] Run full test suite — all passing
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
- [x] Verify `pip install halyard` does not pull in `openai`
