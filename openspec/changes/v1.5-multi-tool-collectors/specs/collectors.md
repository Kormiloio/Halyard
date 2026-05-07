# Spec: Collector Behaviour

Scenarios use WHEN/THEN form. "session" means a correctly-formed `s` line
appended to `ai-sessions.log`.

---

## Codex Desktop importer

**WHEN** `~/.codex/sessions/` does not exist  
**THEN** `import_codex_sessions()` returns `[]` with no error

**WHEN** a session file has `output_tokens == 0`  
**THEN** that session is skipped (plugin-init noise)

**WHEN** a session UUID is already in `~/.halyard/codex-imported`  
**THEN** that session is skipped on re-import

**WHEN** a session is successfully imported  
**THEN** its UUID is appended to `~/.halyard/codex-imported`  
**AND** re-running `import-codex` does not duplicate the record

**WHEN** `cached_input_tokens` is present in the session  
**THEN** `input_tokens` in the written record equals `total_input - cached_input`  
**AND** `cache_read=<cached>` appears in the record

**WHEN** `--dry-run` is passed  
**THEN** no records are written and `~/.halyard/codex-imported` is not updated

---

## Gemini CLI collector

**WHEN** `SessionStart` fires  
**THEN** `~/.halyard/gc-session` is created with `prompt_tokens=0 output_tokens=0 cache_tokens=0`

**WHEN** `AfterModel` fires with a higher `promptTokenCount` than stored  
**THEN** `prompt_tokens` is updated to the new (larger) value

**WHEN** `AfterModel` fires with a lower `promptTokenCount` than stored  
**THEN** `prompt_tokens` is unchanged (it is cumulative; a lower value is a bug in the payload)

**WHEN** `AfterAgent` fires  
**THEN** one session record is written with:
- `input_tokens = prompt_tokens - cache_tokens`
- `output_tokens = sum of candidatesTokenCount from all AfterModel calls`
- `cost_usd = calculate_cost(model, net_input, output_tokens, cache_read=cache_tokens)`
- `billing=api`
- `cache_read=<cache_tokens>` if cache_tokens > 0

**WHEN** `AfterAgent` fires a second time in the same Gemini CLI process  
**THEN** a second record is written (token accumulators reset between turns)

**WHEN** `AfterAgent` fires and `cwd` does not map to any Halyard project  
**AND** no hub is configured  
**THEN** no record is written and the state is reset normally

---

## Cursor collector

**WHEN** `beforeSubmitPrompt` fires and no session file exists  
**THEN** `~/.halyard/cursor-session` is created with the current timestamp

**WHEN** `beforeSubmitPrompt` fires and a session file already exists  
**THEN** the existing file is not overwritten (idempotent)

**WHEN** the `stop` hook fires  
**AND** `workspace_roots` resolves to a Halyard project  
**THEN** one session record is written with `billing=credits` and `tokens_available=false`

**WHEN** the `stop` hook fires  
**AND** `workspace_roots` is non-empty but none resolve to a Halyard project  
**AND** a hub is configured  
**THEN** the record is written to the hub's `ai-sessions.log`

**WHEN** the `stop` hook fires  
**AND** `workspace_roots` is non-empty but none resolve to a Halyard project  
**AND** no hub is configured  
**THEN** no record is written (authoritative workspace given, no match found)

**WHEN** the Claude Code `Stop` hook fires with `cursor_version` in the payload  
**THEN** `claude_code.handle_stop_hook()` returns 0 without writing a record  
**AND** the Cursor `stop` hook handles the record instead

---

## Claude Code collector

**WHEN** the `Stop` hook fires inside a Halyard project tree  
**THEN** a record is written to that project's `ai-sessions.log`  
**WITH** `cost_usd` calculated from the token counts and model

**WHEN** the `Stop` hook fires outside any Halyard project tree  
**AND** a hub is configured  
**THEN** a record is written to the hub's `ai-sessions.log`

**WHEN** the `Stop` hook fires with `cursor_version` present  
**THEN** no record is written (Cursor handles it)

---

## All collectors: project attribution

**WHEN** an active timer is running (`~/.halyard/active` exists with `slug=`)  
**THEN** `project=<active-slug>` is set on the written record (timer wins)

**WHEN** no active timer is running  
**AND** the CWD is inside a git repo with an origin remote  
**AND** `~/.halyard/repos.toml` has a matching entry  
**THEN** `project=<mapped-slug>` is set on the written record

**WHEN** no active timer is running  
**AND** the CWD is inside a git repo with an origin remote  
**AND** no explicit mapping exists  
**THEN** `project=git/<repo-name>` is set on the written record

**WHEN** no active timer and no git remote  
**THEN** `project=` is omitted (session is unattributed)

---

## All collectors: branch tagging

**WHEN** the CWD is inside a git repo on a named branch  
**THEN** `tags=branch:<name>` appears in the written record

**WHEN** the CWD is in a detached HEAD state  
**THEN** no `tags=` key is written for branch

**WHEN** the CWD is not inside a git repo  
**THEN** no `tags=` key is written for branch
