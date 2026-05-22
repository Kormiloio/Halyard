# Halyard Security Review — 2026-05-08

**Reviewer:** Adrian, AppSec Reviewer — Halyard  
**Review Date:** 2026-05-08  
**Codebase Snapshot:** Halyard repository (commit at review time)  
**Scope:** Full static code review across all 10 threat domains defined in Adrian.md  
**Methodology:** Static analysis, pattern matching, data-flow tracing — no live exploitation

> **Status as of 2026-05-22: All findings in this review have been resolved.**
> Both High findings (H-1 CSRF guard, H-2 base_url validation) and the
> Medium/Low items are addressed in mainline code. This document is
> retained as the historical record of the review; per-finding
> resolution notes are inline below. A subsequent review pass
> (2026-05-22) added two further P1 findings around global-state
> integrity sidecar downgrade, also resolved — see commit history.

---

## Executive Summary

Halyard is a well-structured Python CLI application with a local-first threat model. The code is generally clean and security-conscious: subprocess calls avoid shell interpolation, HTML output is consistently escaped via `html.escape()`, the plist generator is XML-safe, and temp-file writes follow atomic rename patterns. No critical vulnerabilities were found.

**Two High findings** required attention before broad deployment (both now resolved):

1. **H-1 (High) — Unauthenticated POST endpoints on ThreadingHTTPServer**: The `/api/start` and `/api/stop` dashboard endpoints write to the user's timeclock file in response to any localhost POST request, with no CSRF protection. Because the server binds on `127.0.0.1` and uses `ThreadingHTTPServer`, any process or browser tab on the same machine can fire these endpoints without restriction.

2. **H-2 (High) — Unvalidated `base_url` passed to OpenAI client**: The `--base-url` value from config or CLI is passed directly to `openai.OpenAI(base_url=...)` without sanitisation. A malicious or misconfigured value in `~/.halyard/log-config.toml` could redirect all session metadata to an arbitrary server.

The remaining findings are Medium or Low severity and are straightforward to remediate.

**Finding Summary:**

| ID    | Severity | Domain                   | Title |
|-------|----------|--------------------------|-------|
| H-1   | High     | Dashboard / HTTP         | Unauthenticated timeclock write via POST |
| H-2   | High     | External Network / AI    | Unvalidated `base_url` for OpenAI client |
| M-1   | Medium   | Log Handling             | Log-line injection via unsanitised `tool` and `model` fields |
| M-2   | Medium   | Log Handling             | `note` and `resume_command` partial sanitisation — spaces still injectable |
| M-3   | Medium   | File I/O / Path Traversal| Invoice path constructed from unsanitised TOML `slug` fields |
| M-4   | Medium   | Subprocess               | `render_pdf` and `_open_file` pass unsanitised `invoice_path` to subprocess |
| M-5   | Medium   | Session & Log            | Quarantine file (`quarantine.log`) writes original malformed line unescaped |
| M-6   | Medium   | Credential Management    | `ANTHROPIC_API_KEY` error message echoed verbatim in `LogAgentError` chain |
| L-1   | Low      | Config / TOML            | Jinja2 environment created with `autoescape=False` for Markdown template |
| L-2   | Low      | Subprocess               | `launchctl unload` called without `check=True` — silent failure on uninstall |
| L-3   | Low      | File I/O                 | `assign_unattributed_sessions` writes log non-atomically |
| L-4   | Low      | Dependency               | Broad version pins allow future vulnerable minor releases |
| L-5   | Low      | .gitignore               | `~/.halyard/pricing.toml` (remote-fetched content) not in `.gitignore` |

---

## Domain 1: Credential & Secret Management

### M-6 — API Key Reflected in Error Chain

**Location:** `src/halyard/log_agent.py`, line 322  
**Severity:** Medium  
**CWE:** CWE-209 (Generation of Error Message Containing Sensitive Information)

**Threat Scenario:**  
```python
except anthropic.AnthropicError as exc:
    raise LogAgentError(f"Anthropic API error: {exc}") from exc
```
The `AnthropicError` exception from the SDK can contain the full HTTP response body from Anthropic's API, which in some error cases (e.g., 401 Unauthorized) may echo back a partial or full API key, the request headers, or other request-level context. This `LogAgentError` message is then printed to the terminal by the CLI and may end up in shell history, log files, or bug reports.

**Remediation:**
```python
except anthropic.AnthropicError as exc:
    # Don't forward SDK exception text — it may contain request context
    raise LogAgentError(
        f"Anthropic API error: {type(exc).__name__} — check your ANTHROPIC_API_KEY."
    ) from exc
```
Apply the same pattern to the OpenAI exception handler at line 449.

**Verification:** Trigger an intentional 401 error (bad key), observe that the printed error message contains no key material or HTTP header content.

---

**Other credential observations (no finding):**

- API keys are read exclusively from environment variables (`os.environ.get`), never from files or hardcoded strings. Correct.
- Keys are passed to SDK clients immediately and not stored on the `AiSession` object or written to any log file. Correct.
- The `.gitignore` correctly excludes `halyard.toml`, `clients.toml`, `projects.toml`, and `ai-sessions.log`. These are the files that could contain financial data.
- No pickle, shelve, or other binary serialisation of credentials found.

---

## Domain 2: Subprocess & Shell Injection Prevention

### M-4 — Invoice Path Passed to `typst` and `open`/`xdg-open` Without Normalisation

**Location:** `src/halyard/invoicing.py`, lines 318, 327, 333  
**Severity:** Medium  
**CWE:** CWE-78 (Improper Neutralisation of Special Elements in OS Command — Shell Injection)

**Threat Scenario:**
```python
def render_pdf(invoice_path: Path) -> str | None:
    subprocess.run(["typst", "compile", str(invoice_path)], check=True)
    _open_file(invoice_path.with_suffix(".pdf"))

def _open_file(path: Path) -> None:
    if _sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
```
`invoice_path` is assembled from TOML-derived `client_slug` and a period string in `generate_invoice()` (line 185):
```python
invoice_path = invoice_dir / f"{invoice_number}-{client_slug}.md"
```
If `client_slug` contains characters such as `../` (path traversal) or a space (argument splitting for `open`/`xdg-open`), the path passed to subprocess could behave unexpectedly. All calls use list form (no shell=True), so shell injection is not possible, but path traversal is: a slug like `../../etc/cron.d/evil` would construct a path outside the invoices directory.

The list-form subprocess invocations protect against shell injection — this is not a shell injection finding. The residual risk is controlled path traversal and unexpected argument splitting in `open`/`xdg-open` when a slug contains spaces.

**Remediation:**  
Validate `client_slug` at parse time in `_read_clients()` to enforce the documented format (lowercase letters, digits, hyphens):
```python
import re
_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,63}$')

if not _SLUG_RE.match(slug):
    continue  # silently skip malformed slug, or raise InvoiceError
```
Also validate `project_slug` in `_read_projects()` with the same pattern.

**Verification:** Attempt to generate an invoice with a client slug of `../evil` and confirm the path is rejected before reaching the subprocess call.

---

### L-2 — `launchctl unload` Called Without `check=True`

**Location:** `src/halyard/service.py`, line 26  
**Severity:** Low  
**CWE:** CWE-390 (Detection of Error Condition Without Action)

**Threat Scenario:**
```python
subprocess.run(["launchctl", "unload", "-w", str(PLIST_PATH)], check=False)
```
`uninstall_service()` silently ignores failure from `launchctl unload`. If the service is in a partially loaded state and the unload fails, the user will not be informed, and `PLIST_PATH.unlink()` on line 27 will still remove the plist. The service process may continue running orphaned with no way to cleanly stop it.

**Remediation:**
```python
result = subprocess.run(
    ["launchctl", "unload", "-w", str(PLIST_PATH)],
    capture_output=True, text=True
)
if result.returncode != 0:
    # Warn but do not abort — still remove the plist
    print(f"[halyard] Warning: launchctl unload exited {result.returncode}: {result.stderr.strip()}", file=sys.stderr)
```

**Verification:** Manually corrupt the plist label and run `halyard service uninstall`; confirm the warning is printed and the plist file is still removed.

---

**Other subprocess observations (no finding):**

- `git_context.py`: All `git` subprocess calls use list form, set `timeout=2`, and handle `TimeoutExpired` and `OSError`. The `capture_output=True` pattern is correct. No `cwd` parameter is user-controllable beyond the current working directory already trusted by the OS.
- `config_history.py`: `git log --follow -p -- clients.toml` runs with `cwd=project_dir` (trusted Halyard project root), list form, and `timeout=10`. The parsed output is processed with regex, not re-executed.
- `orchestration.py` (`_detect_business_name`): `git config user.name` is read-only, list form, with `timeout=3`. Result is used only as a display string in a template — not executed.
- `service.py` `install_service`: `launchctl load` uses `check=True`. Correct. The plist XML embeds `project_dir` and `halyard_exe` as `<string>` values inside `<array>` elements — these are not shell-interpolated by launchctl. The path values could contain XML special characters (`<`, `>`, `&`), but because they appear inside `<string>` tags that form the `ProgramArguments` array, launchctl parses them safely as arguments. No finding.

---

## Domain 3: Configuration File Parsing & Injection

**Observations (no standalone high/medium findings):**

- `pricing.py`: `_parse_models_table()` validates that `input` and `output` values are `int | float` and `> 0` before accepting them. The minimum-3-models check prevents truncated responses from silently replacing the pricing table. Correct.
- `invoicing.py`: `_read_clients()` and `_read_projects()` iterate TOML arrays, check `isinstance(raw, dict)` before field access, and apply `str()` / `float()` coercions with fallbacks. No type confusion vulnerability found.
- `git_context.py`: `_load_repos_config()` applies `isinstance(k, str) and isinstance(v, str)` filtering before returning the mapping. Correct.
- TOML parsing uses the stdlib `tomllib` (Python 3.11+). No known deserialization attacks exist in `tomllib`; it is a pure parser with no code execution path.

### L-1 — Jinja2 `autoescape=False` for Invoice Rendering

**Location:** `src/halyard/invoicing.py`, line 519  
**Severity:** Low  
**CWE:** CWE-116 (Improper Encoding or Escaping of Output)

**Threat Scenario:**
```python
env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
```
The invoice template renders client names, addresses, and business data into Markdown. `autoescape=False` is the correct default for Markdown output (HTML escaping would corrupt the Markdown). However, if the template is ever changed to emit HTML (e.g., a future `invoice.html.j2` added alongside the existing `.md.j2`), the `autoescape=False` setting would silently expose any HTML-injection path. The risk is low in the current state (Markdown output), but it should be documented.

**Remediation:**  
Add a comment at the `Environment` construction site:
```python
# autoescape=False is intentional: output is Markdown, not HTML.
# If adding HTML templates in future, create a separate Environment with autoescape=True.
env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
```

**Verification:** No runtime change required; this is a code-comment documentation fix.

---

## Domain 4: File I/O & Path Traversal

### M-3 — Invoice Filename Constructed From Unvalidated TOML `slug`

**Location:** `src/halyard/invoicing.py`, lines 183–185  
**Severity:** Medium  
**CWE:** CWE-22 (Path Traversal)

**Threat Scenario:**
```python
invoice_number = f"{period}-{counter + 1:03d}"
invoice_path = invoice_dir / f"{invoice_number}-{client_slug}.md"
```
`client_slug` comes from `clients.toml` via `_read_clients()`. While `clients.toml` is user-owned, a crafted entry like `slug = "../../.bash_profile"` would cause `invoice_path` to resolve outside the `invoices/` subdirectory. The file would be written (or overwritten) at that location when `invoice_path.write_text(rendered)` is called on line 221.

This is an integrity risk: a user who copy-pastes a configuration snippet from an untrusted source (e.g., a blog post, a gist) could silently overwrite files outside the Halyard project directory.

**Remediation:**  
Validate slug format in `_read_clients()` before accepting it (see also M-4 remediation above), and add a path containment check before writing:
```python
invoice_path = invoice_dir / f"{invoice_number}-{client_slug}.md"
# Ensure the resolved path stays within invoice_dir
if not invoice_path.resolve().is_relative_to(invoice_dir.resolve()):
    raise InvoiceError(f"Invoice path escapes invoice directory: {invoice_path}")
```

**Verification:** Create a `clients.toml` entry with `slug = "../../evil"`, run `halyard invoice`, and confirm the path is rejected.

---

### L-3 — Non-Atomic Log Rewrite in `assign_unattributed_sessions`

**Location:** `src/halyard/ai_log.py`, lines 159–161  
**Severity:** Low  
**CWE:** CWE-362 (Concurrent Execution Using Shared Resource Without Proper Synchronization — Race Condition)

**Threat Scenario:**
```python
if changed:
    log_path.write_text("\n".join(lines) + "\n")
```
`assign_unattributed_sessions()` reads the log, modifies lines in memory, then writes the full file back with `write_text()`. If the process is interrupted between the read and write (SIGKILL, power loss) or if a collector appends a session concurrently, the new entries are lost. The `_rewrite_lines_atomic()` helper in `orchestration.py` already implements the correct pattern (write temp, then `replace()`), but it is not used here.

**Remediation:**
```python
if changed:
    tmp = log_path.with_suffix(".log.tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(log_path)
```

**Verification:** The `backfill_window()` function in `ai_log.py` (line 354) has the same pattern and should receive the same fix.

---

**Other file I/O observations (no finding):**

- `pricing.py` atomic write: `tempfile.mkstemp` + `os.fdopen` + `os.replace` pattern is correct. The `suppress(OSError)` on the cleanup path is appropriate.
- `db.py`: SQLite path is hardcoded to `~/.halyard/cache.db`. Not user-controllable. No path traversal risk.
- `ai_log.py` `append_session`: Opens in append mode (`"a"`), which is atomic at the OS level for single-line writes on macOS/Linux. Correct for this use case.

---

## Domain 5: Session & Log Data Handling

### M-1 — Log-Line Injection via Unsanitised `tool` and `model` Fields

**Location:** `src/halyard/ai_log.py`, lines 66–68 (in `to_log_line()`)  
**Severity:** Medium  
**CWE:** CWE-93 (Improper Neutralisation of CRLF Sequences — Log Injection)

**Threat Scenario:**
```python
parts = [
    "s",
    self.start.strftime("%Y-%m-%dT%H:%M:%S"),
    self.end.strftime("%Y-%m-%dT%H:%M:%S"),
    self.tool,   # <-- no sanitisation
    self.model,  # <-- no sanitisation
    ...
]
```
The `tool` and `model` fields are taken directly from the JSON payload supplied by Claude Code's Stop hook, Cursor's stop hook, and Gemini's AfterModel hook. An adversarial or compromised hook payload containing spaces, newlines, or `key=value` patterns (e.g., `model = "cursor\ncost_usd=0.0000 project=evil:client"`) could inject additional fields into the log line or insert entirely new log lines.

When `parse_sessions()` later reads the log, it splits on whitespace and processes `key=value` tokens — injected tokens would be parsed and silently accepted.

**Remediation:**  
Sanitise `tool` and `model` in `to_log_line()` before embedding in the log line:
```python
def _safe_field(value: str) -> str:
    """Remove whitespace and characters that could break the log line format."""
    return re.sub(r'[\s=]', '_', value)[:128]

parts = [
    "s",
    self.start.strftime("%Y-%m-%dT%H:%M:%S"),
    self.end.strftime("%Y-%m-%dT%H:%M:%S"),
    _safe_field(self.tool),
    _safe_field(self.model),
    ...
]
```
Also validate `tool` and `model` in `_parse_line_result()` to reject lines where these fields contain spaces or `=` characters (treat as quarantine candidates).

**Verification:** Pass `model = "bad model\n s 2026-01-01T00:00:00 2026-01-01T01:00:00 fake fake 0 0 0.0"` through `to_log_line()` and confirm the injected newline is stripped before writing.

---

### M-2 — Partial Sanitisation of `note` and `resume_command` Allows Space Injection

**Location:** `src/halyard/ai_log.py`, lines 96–99 and 118–119  
**Severity:** Medium  
**CWE:** CWE-93 (Log Injection)

**Threat Scenario:**
```python
note_safe = (
    self.note.replace("\n", " ").replace("\r", "").replace("\t", " ").replace(" ", "_")
)
kvs.append(f"note={note_safe}")
```
Newlines and tabs are stripped, and spaces are replaced with underscores. However, when `_parse_line_result()` reads the log back (line 260), it reverses this:
```python
case "note":
    session.note = v.replace("_", " ")
```
This round-trips correctly. The risk is a different one: `note` values containing literal `_key=value_` substrings that look like injected KV tokens after underscore-to-space inversion during parsing are not possible (the `=` sign would be parsed as part of the note value since the parser splits on `=` only once per token). **However**, the `resume_command` field performs the same underscore substitution:
```python
safe_cmd = self.resume_command.replace(" ", "_").replace("\n", "").replace("\r", "")
kvs.append(f"resume_command={safe_cmd}")
```
A `resume_command` value containing a literal `=` character (valid in shell commands, e.g., `gemini --resume abc=123`) would produce `resume_command=gemini_--resume_abc=123`. When parsed, the split at `=` produces `k="resume_command"`, `v="gemini_--resume_abc=123"` — which round-trips correctly. No injection is possible here through the current parser. But neither `note` nor `resume_command` reject or escape `=` in their input, meaning a value containing ` project=evil:client` (with a leading space — blocked by the space→underscore conversion) is sanitised. A value containing `project=evil:client` without a leading space **would** appear inside the note/resume_command value without triggering a new KV token, because the parser requires whitespace separation between tokens.

The actual residual risk: the `model` and `tool` fields (covered in M-1) are the real injection vectors. For `note` and `resume_command`, the sanitisation is functionally adequate but not documented, creating a maintenance trap if the log format changes.

**Remediation:**  
Add a comment explaining the encoding contract for these fields, and consider a more explicit codec (e.g., percent-encoding) rather than underscore substitution to avoid the round-trip ambiguity with legitimate underscores:
```python
# note is encoded: spaces→underscores, newlines stripped.
# Underscores in original notes become indistinguishable from encoded spaces.
# Future format versions should use percent-encoding.
```

**Verification:** Round-trip a note containing literal underscores through `to_log_line()` and `from_log_line()` to confirm the ambiguity. No security fix needed in the current format, but document the limitation.

---

### M-5 — Quarantine File Writes Original Malformed Line Unescaped

**Location:** `src/halyard/ai_log.py`, lines 402–407  
**Severity:** Medium  
**CWE:** CWE-116 (Improper Encoding or Escaping of Output)

**Threat Scenario:**
```python
def _write_quarantine(original_line: str, error: str) -> Path:
    path = Path.home() / ".halyard" / "quarantine.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(f"; error={error}\n")
        f.write(original_line.rstrip("\n") + "\n")
    return path
```
The `error` string written to `quarantine.log` can contain user-controlled content from the log line itself — for example, `_parse_line_result()` returns errors like `f"invalid start timestamp: {parts[1]}"`. If `parts[1]` (the timestamp field from an adversarial log line) contains newlines, it would inject additional lines into `quarantine.log`. A subsequent tool that reads `quarantine.log` expecting `;`-prefixed comment lines followed by a raw data line could be confused.

More concretely, the `error` field written as `; error=...` does not escape the value. An adversarial error string containing `\n; error=injected` would produce a second `; error=` line.

**Remediation:**
```python
safe_error = error.replace("\n", " ").replace("\r", "")
f.write(f"; error={safe_error}\n")
```

**Verification:** Pass a malformed log line where the timestamp field contains `\n; error=injected` and confirm quarantine.log contains only one `;` header line per quarantined entry.

---

## Domain 6: HTTP Dashboard Security

### H-1 — Unauthenticated Timeclock Write via POST Endpoints

**Location:** `src/halyard/dashboard.py`, lines 69–109  
**Severity:** High  
**CWE:** CWE-352 (Cross-Site Request Forgery), CWE-306 (Missing Authentication for Critical Function)

**Threat Scenario:**
```python
def do_POST(self) -> None:
    length = int(self.headers.get("Content-Length", 0))
    body = self.rfile.read(length).decode(errors="replace") if length else ""
    params = {k: v[0] for k, v in parse_qs(body).items()}

    if self.path == "/api/start":
        slug = params.get("project", "").strip()
        if (slug and "/" in slug and ...):
            with timeclock.open("a") as f:
                f.write(f"i {ts} {account}\n")
```
The dashboard binds to `127.0.0.1` only, which prevents access from the network. However, any process running as the same user on the same machine can POST to `http://127.0.0.1:7432/api/start` and inject arbitrary timeclock entries. More significantly, a malicious browser tab open on the same machine can trigger this via a cross-origin form POST (form submissions to `http://` origins are not blocked by the Same-Origin Policy, only by CORS — which applies to XHR/fetch, not form POSTs). A browser visiting a malicious page while the Halyard dashboard is running could silently start or stop the user's timeclock.

The `slug` validation on line 80 (`"/" in slug and not slug.startswith("/") and not slug.endswith("/")`) prevents empty or absolute-path slugs, but does not prevent injection of arbitrary project names.

**Remediation — Option A (Recommended): Origin check:**
```python
def do_POST(self) -> None:
    origin = self.headers.get("Origin", "")
    referer = self.headers.get("Referer", "")
    allowed_origins = {f"http://127.0.0.1:{server_port}", f"http://localhost:{server_port}"}
    # Browsers always send Origin on cross-site form POSTs; reject if it doesn't match
    if origin and origin not in allowed_origins:
        self.send_error(HTTPStatus.FORBIDDEN, "Cross-origin POST not allowed")
        return
```

**Remediation — Option B: CSRF token:**  
Embed a random token in the dashboard HTML forms and validate it on every POST. Simplest implementation: generate a token at server startup, store it in a closure variable, embed it as a hidden field in each form, and reject POSTs where the token is absent or wrong.

**Verification:** With the dashboard running, use `curl -X POST http://127.0.0.1:7432/api/start -d "project=evil/project"` from the terminal and confirm the request is rejected (or, before fix, observe the timeclock entry being written).

---

**Other dashboard observations (no finding):**

- All data values rendered into HTML pass through `_e()` → `html.escape()`. Project names, model names, slugs, and timestamps are all escaped. No XSS path found.
- The dashboard is localhost-only by design (binds `127.0.0.1`). No credential material (API keys) is rendered in the dashboard HTML.
- `Content-Length` parsing: `int(self.headers.get("Content-Length", 0))` — if `Content-Length` is a non-integer string, `int()` will raise `ValueError`. The `BaseHTTPRequestHandler` framework will handle this as an uncaught exception, resulting in a 500 response but no security impact.
- No persistent session state, no cookies, no authentication — consistent with the local threat model.
- The `meta http-equiv="refresh" content="10"` auto-refresh is benign (no user data sent in the refresh).

---

## Domain 7: External Network Requests

### H-2 — Unvalidated `base_url` for OpenAI-Compatible Client

**Location:** `src/halyard/log_agent.py`, lines 353–356  
**Severity:** High  
**CWE:** CWE-918 (Server-Side Request Forgery — SSRF), CWE-346 (Origin Validation Error)

**Threat Scenario:**
```python
client = openai.OpenAI(
    api_key=api_key or "local",
    base_url=base_url,  # <-- from config or --base-url flag
)
```
`base_url` comes from `cfg.openai_base_url` (loaded from `~/.halyard/log-config.toml`) or from the `--base-url` CLI flag. No validation is performed on this value before it is passed to the SDK client. A malicious `log-config.toml` (e.g., planted by another process running as the same user, or from a misconfigured dotfile) could set `openai_base_url = "http://attacker.example.com/v1"`. All subsequent `halyard log --agent openai` queries — including the user's query text and session metadata — would be sent to that endpoint.

In the local threat model, this is a realistic risk: the `~/.halyard/` directory is user-writable, and Halyard never validates that `log-config.toml` was written by Halyard itself. A social engineering attack ("add this to your log-config.toml to enable feature X") is plausible.

**Remediation:**
```python
from urllib.parse import urlparse

def _validate_base_url(url: str) -> str:
    """Require HTTPS or localhost HTTP. Raise LogAgentError otherwise."""
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return url
    if parsed.scheme == "http":
        host = parsed.hostname or ""
        if host in ("127.0.0.1", "localhost", "::1"):
            return url
    raise LogAgentError(
        f"Invalid base_url {url!r}: must be HTTPS or a localhost HTTP URL. "
        "Use https://api.openai.com/v1 for OpenAI or http://localhost:PORT/v1 for local servers."
    )
```
Call `_validate_base_url(base_url)` before constructing the OpenAI client.

**Verification:** Set `openai_base_url = "http://example.com/v1"` in `~/.halyard/log-config.toml` and confirm `halyard log --agent openai` raises a `LogAgentError` before making any network request.

---

**Other network observations (no finding):**

- `pricing.py` `update_pricing()`: Uses `urllib.request.urlopen` with an explicit `timeout=5`. The URL is hardcoded to `_REMOTE_URL = "https://raw.githubusercontent.com/..."` — not user-controllable at runtime. HTTPS is enforced by the URL scheme. Certificate validation is handled by Python's default SSL context (system trust store). No SSRF risk.
- The Anthropic SDK enforces HTTPS for all API calls. No configuration path allows HTTP for `run_claude_log_query()`.

---

## Domain 8: JSON & Data Deserialization

**Observations (no high/medium finding):**

All JSON parsing in collectors uses `json.loads()` with a try/except guard that returns `{}` or `None` on failure. Specifically:

- `claude_code.py` `_read_payload()` (line 122): Catches `json.JSONDecodeError` and `ValueError`, returns `{}`.
- `cursor.py` `_read_payload()` (line 136): Same pattern.
- `gemini_cli.py` `_read_payload()` (line 220): Same pattern.
- `codex_app.py` `_parse_session_file()` (line 111): Per-line `json.loads` with `continue` on `JSONDecodeError`.
- `gemini_history.py` `parse_session_file()` (line 77): Wraps the entire parse in `try/except Exception: return None`.

No use of `pickle`, `yaml.load()` (unsafe), `eval()`, `exec()`, or `marshal` was found anywhere in the codebase. Deserialization is limited to `json.loads()` and `tomllib.loads()`, both of which have no code execution paths.

The `gemini_history.py` parser accepts arbitrary JSON from `~/.gemini/tmp/*/chats/session-*.json`. These files are written by the Gemini CLI itself, not by Halyard. The fields extracted (`sessionId`, `model`, token counts) are all cast to `str` or `int` with defensive fallbacks. No gadget chain risk.

---

## Domain 9: AI Agent Loop & Tool Use Security

**Observations (no high/medium finding):**

`log_agent.py` `_execute_tool()` (line 453) is the tool dispatcher for the Claude and OpenAI agentic loops. Key observations:

- **Allowlist dispatch**: Tool routing uses a series of `if name ==` comparisons against a hardcoded allowlist (`read_sessions`, `summarize_by_project`, `summarize_by_model`, `read_timeclock`). Unknown tool names return `{"error": "Unknown tool: {name}"}` rather than executing anything. This is the correct pattern.
- **No shell execution from tool calls**: Tool implementations call Python functions (`parse_sessions`, `parse_timeclock`, `summarize_ai_sessions`) — no subprocess calls are triggered from tool results.
- **Loop limit**: Both the Claude and OpenAI loops enforce a maximum of 3 turns (`for _ in range(3):`), preventing runaway agent loops. Correct.
- **Tool args are not user-controlled at the shell level**: Tool arguments are structured JSON from the LLM response, not shell strings. The `start_date`/`end_date` arguments are parsed by `_parse_date()` which validates ISO format and returns `None` on failure — safe.
- **`limit` parameter**: The `read_sessions` tool accepts a `limit` integer from the LLM. There is no server-side cap beyond Python's memory. An LLM could request `limit=2147483647`, causing `parse_sessions()` to read and return all sessions. This is a DoS edge case, not a security finding, but worth noting.
- **Query text as user input to LLM**: The user's natural-language query is passed as the `content` field of the first `user` message. This is the intended design. No system prompt injection protection is applied, but the query is explicitly labelled as user content (not system prompt), which is the correct usage.
- **Session data returned to LLM**: `parse_sessions()` returns `AiSession` objects serialised via `dataclasses.asdict()`. These contain `tool`, `model`, `project`, `cost_usd`, and token counts — no API keys, no file paths beyond project slugs, no personally identifying information beyond what the user explicitly logged. Acceptable data exposure for the local threat model.

---

## Domain 10: Dependency & Supply Chain

### L-4 — Broad Version Pins Allow Future Vulnerable Releases

**Location:** `pyproject.toml`, lines 20–30  
**Severity:** Low  
**CWE:** CWE-1357 (Reliance on Insufficiently Trustworthy Component)

**Current pins:**
```toml
"anthropic>=0.40"
"jinja2>=3.1"
"typer>=0.12"
"rich>=13.7"
"pydantic>=2.6"
"tomli-w>=1.0"
"dateparser>=1.2"
"textual>=0.60"
"watchfiles>=0.21"
```

All lower-bound-only pins (`>=`) allow `pip` to install any future release, including releases that may introduce vulnerabilities. The `anthropic` and `jinja2` packages are particularly sensitive: Jinja2 has had injection vulnerabilities in older versions, and the Anthropic SDK handles API key transmission.

No known CVEs affect the listed minimum versions as of 2026-05 for the critical dependencies (`anthropic>=0.40`, `jinja2>=3.1.4`).

**Remediation:**  
For a CLI application distributed via `pip`, the current approach (lower-bound pins) is standard and acceptable. The higher-risk action is to adopt a lockfile for development and CI:
```
pip-compile --generate-hashes pyproject.toml
```
For production distribution, consider adding upper bounds on the highest-risk packages:
```toml
"anthropic>=0.40,<2.0"
"jinja2>=3.1,<4.0"
```

**Verification:** Run `pip-audit` against the installed dependencies in CI to catch newly disclosed CVEs on each build.

---

### L-5 — `~/.halyard/pricing.toml` Not in Project `.gitignore`

**Location:** `.gitignore` (root), `src/halyard/pricing.py` line 50  
**Severity:** Low  
**CWE:** CWE-312 (Cleartext Storage of Sensitive Information)

**Threat Scenario:**  
`pricing.py` fetches remote pricing data and writes it to `~/.halyard/pricing.toml`. This file lives outside the project root, so it is not subject to the project `.gitignore`. However, the `.gitignore` does include `halyard.toml`, `clients.toml`, and `invoices/` — which contain financial data. The pricing file itself is not sensitive (it contains only model pricing rates, no user data), but the omission is worth documenting for completeness.

More importantly: the project `.gitignore` does not include `~/.halyard/` itself, which means a developer who accidentally initialises their Halyard project inside `~` would expose `unattributed.log`, `quarantine.log`, `cc-session`, and the `active` file. The `.gitignore` generated by `scaffold_project()` in `orchestration.py` (line 99) includes `.halyard-cache/` but not `.halyard/`.

**Remediation:**  
Add `.halyard/` to the scaffold-generated `.gitignore` template in `orchestration.py`:
```python
_GITIGNORE = """\
# Halyard
.halyard/
.halyard-cache/
.DS_Store
...
```

**Verification:** Run `halyard init` in a temp directory and confirm `.gitignore` contains `.halyard/`.

---

## Dependency Scan Notes

No `pip-audit` or `safety` scan was performed in this static review. The following packages are recommended for a live vulnerability scan before the next release:

| Package | Min Version | Notes |
|---------|-------------|-------|
| `anthropic` | 0.40 | API key transmission; keep current |
| `jinja2` | 3.1 | Template rendering; patch history includes injection fixes |
| `pydantic` | 2.6 | Active development; v2.x has had validation bypass fixes |
| `dateparser` | 1.2 | Complex parsing; REDOS risk in older versions |

**Recommended action:** Run `pip-audit --requirement requirements.txt` or `safety check` in CI against the pinned development lockfile.

---

## Audit Trail

### Review Methodology
1. Read all 47 Python source files in `src/halyard/` and `src/halyard/collectors/`
2. Mapped data flows for each of the 10 threat domains
3. Applied pattern matching for known vulnerability signatures:
   - Shell injection: `shell=True`, f-string interpolation into `subprocess.run`
   - Path traversal: string concatenation into `open()` / `Path()` / `write_text()`
   - Log injection: unsanitised fields written to append-mode log files
   - CSRF: POST endpoints without origin/referer validation
   - Credential leak: exception messages containing SDK exception text
   - SSRF: user-controlled URLs passed to HTTP clients
4. Reviewed `pyproject.toml` for dependency versions
5. Reviewed `.gitignore` for sensitive file exclusions
6. No dynamic testing, fuzzing, or live execution performed

### Files Reviewed
All files under `src/halyard/` including:
- Core: `ai_log.py`, `log_agent.py`, `pricing.py`, `dashboard.py`, `invoicing.py`, `orchestration.py`, `service.py`, `git_context.py`, `config_history.py`, `repl.py`, `db.py`
- Collectors: `claude_code.py`, `cursor.py`, `gemini_cli.py`, `gemini_history.py`, `codex_app.py`
- Configuration: `pyproject.toml`, `.gitignore`

### Confidence Level
**High** for the threat domains reviewed. Static analysis on a well-structured codebase with consistent patterns. The primary area of lower confidence is the agent loop (Domain 9) — dynamic testing of the Claude/OpenAI tool-use loop against adversarial LLM responses was not performed.

### Recommended Next Steps

1. **Before production deployment:** Remediate H-1 (CSRF on POST endpoints) and H-2 (unvalidated `base_url`).
2. **Before next release:** Address M-1 (log injection via tool/model fields) and M-3 (invoice path traversal).
3. **Ongoing:** Add `pip-audit` to CI pipeline. Add slug validation regex to `_read_clients()` and `_read_projects()`.
4. **Future consideration:** Adopt atomic writes (`write-then-rename`) consistently across all log mutation functions.

---

**Sign-off:**  
Adrian — AppSec Reviewer, Halyard  
Review completed: 2026-05-08  
Scope: Static code review of full `src/halyard/` tree, `pyproject.toml`, `.gitignore`  
Next review recommended: After remediation of H-1 and H-2, or before v1.0 release.
