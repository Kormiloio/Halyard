# Halyard — Comprehensive Security Architecture Review
## 2026-05-08

**Reviewer:** Sage, Senior AppSec Engineer  
**Review Date:** 2026-05-08  
**Codebase Snapshot:** Halyard repository (commit at review time)  
**Scope:** Architectural, design-level, and assurance review — not a re-run of Adrian's targeted vulnerability scan  
**Prior Work Baseline:** Adrian's review (2026-05-08), 11 findings (2 High, 5 Medium, 5 Low), all remediated by Kai. 39 security tests added post-remediation.  
**Methodology:** Full source read (47 Python files, ~10K LOC), full test suite read (39 files), data-flow tracing, trust model analysis, implicit assumption surfacing. No live execution or fuzzing.

> **Status note (2026-05-22):** The Adrian/Kai baseline findings (11 items)
> are resolved — see `security-review-2026-05-08.md`. The five design-level
> risks (D-1…D-5) below are architectural by nature; their resolution
> status is tracked in `openspec/` changesets (e.g. v2.40 HMAC authenticated
> state integrity addresses parts of D-2/D-3) and is not implied by this
> document. Read each finding alongside the most recent codebase before
> acting.

---

## 1. Executive Summary

Halyard is a local-first Python CLI for AI work intelligence. Its threat model is coherent and well-suited to a single-user, trusted-OS deployment: no server component, no multi-tenant access control, no stored credentials, no remote listening port accessible from the network. The post-remediation codebase is clean by pattern-matching standards — Adrian's findings represent genuine tactical improvements, and Kai's fixes are well-applied.

This review takes the architectural lens that static pattern scanning cannot. The findings below are design-level: they describe structural properties of the system that create lasting risk exposure across the application's lifetime, not individual lines that can be patched in isolation. None rise to the level of an immediately exploitable vulnerability in the application's stated threat model. Several would become critical if the threat model assumptions break — which is the point of architectural review.

### Top 5 Design-Level Risks

**D-1 (High) — Session Attribution Is a Trust Claim, Not a Verified Fact**  
Session attribution — the assignment of a captured session to a project and thus to an invoice — relies on a chain of inferences (git remote lookup, timeclock overlap, active-timer file, hook payload `workspace_roots`) that is never cryptographically bound to either the session or the log entry. The audit trail records what project a session was attributed to, but not *how* or *why*. This makes the cost and invoicing system vulnerable to undetected attribution drift under normal operating conditions, and vulnerable to deliberate manipulation by anyone who can write to `~/.halyard/` or the git working tree.

**D-2 (High) — The `~/.halyard/active` File Is a Single-Writer, Unguarded State Channel**  
Three independent collectors (Claude Code, Cursor, Gemini CLI) all read and write `~/.halyard/active` to determine the currently active project. There is no file locking, no ownership check, and no version field. A race condition between a Cursor session stop and a Claude Code session start can produce a session attributed to the wrong project. On a system where two collectors fire simultaneously (common during multi-tool workflows), cost attribution silently breaks.

**D-3 (Medium) — Org Identity Resolution Has No Integrity Check on `org.toml`**  
`org.toml` is the source of truth for email-to-team mapping in the multi-user org sync path. The sync pipeline reads this file and uses it to assign every session to a team and user identity for financial reporting. Any contributor who can write to the hub directory can modify `org.toml` — claiming sessions under another team, re-routing cost attribution, or suppressing their own sessions from the org store. There is no hash, signature, or write-audit on `org.toml` itself.

**D-4 (Medium) — Pricing Table Integrity Is Validated but Not Authenticated**  
`update_pricing()` validates that the downloaded TOML has the correct structure and positive prices — but it fetches from a hardcoded GitHub raw URL over HTTPS with system CA validation. If the GitHub repository is compromised, a malicious pricing table passes all validation checks and silently inflates or deflates every future cost calculation. Invoices sent to clients could be wrong. There is no pinned hash, no signature, and no staleness alert tied to invoice generation.

**D-5 (Medium) — The Dashboard CSRF Guard Has a Structural Blind Spot**  
The `Origin`-header CSRF guard (H-1 fix) is the right approach, but it explicitly allows all requests with no `Origin` header — including those from local scripts. This means any shell script, cron job, or background process running as the same user can manipulate the timeclock without restriction. The guard protects against browser-based CSRF from remote pages, not against local attacker processes. The documentation of this intentional choice in the code (`curl/CLI calls ... still permitted`) is correct, but the implication — that local process isolation is the only remaining defence — is undocumented and easy to miss.

### Overall Confidence and Scope Limitations

**Confidence: High** for static architectural analysis. The codebase is well-structured, consistently styled, and straightforward to trace. Lower confidence on:

- The agent loop under adversarial LLM responses (no dynamic testing performed)
- The Gemini history parser under unusual session file structures from future Gemini CLI versions
- Race conditions in concurrent collector execution (no threading analysis beyond code reading)
- Windows and NFS behaviour of POSIX atomicity assumptions (stated scope exclusion; flagged below)

---

## 2. Architecture Review

### 2.1 Trust Boundary Diagram

The following describes the principal trust boundaries in data flow order. Each boundary is a point where data crosses from one trust context to another.

```
┌─────────────────────────────────────────────────────────┐
│  EXTERNAL / UNTRUSTED                                   │
│                                                         │
│  ┌────────────────┐  ┌───────────────┐  ┌────────────┐ │
│  │  Claude Code   │  │    Cursor     │  │ Gemini CLI │ │
│  │  Stop hook     │  │  stop hook    │  │AfterAgent  │ │
│  │  (stdin JSON)  │  │ (stdin JSON)  │  │(stdin JSON)│ │
│  └───────┬────────┘  └───────┬───────┘  └─────┬──────┘ │
└──────────┼────────────────────┼────────────────┼────────┘
           │  TRUST BOUNDARY 1: Hook payload reception     │
           ▼                    ▼                ▼
┌─────────────────────────────────────────────────────────┐
│  COLLECTOR LAYER (src/halyard/collectors/)              │
│  claude_code.py / cursor.py / gemini_cli.py             │
│                                                         │
│  Token counts parsed from payload (int() with fallback) │
│  Model name taken from payload (sanitized via M-1 fix)  │
│  CWD from payload.workspace_roots (trusted as Path)     │
│  Project from active file or git inference              │
└──────────────┬───────────────────────────────────────────┘
               │  TRUST BOUNDARY 2: Collector → Log write
               ▼
┌─────────────────────────────────────────────────────────┐
│  SESSION LOG (~/.halyard/unattributed.log OR            │
│               <project>/ai-sessions.log)                │
│                                                         │
│  Append-only on POSIX; no locking; no MAC; no sig       │
│  Parsed by read_text().splitlines() on every access     │
└──────────────┬───────────────────────────────────────────┘
               │  TRUST BOUNDARY 3: Log → Application state
               ▼
┌─────────────────────────────────────────────────────────┐
│  PARSE + ENRICH LAYER (ai_log.py, reports.py)           │
│                                                         │
│  _parse_line_result(): validates types, rejects negatives│
│  Quarantines malformed lines (does not fail silently)   │
│  git context added: current_branch(), infer_project()   │
└──────────────┬───────────────────────────────────────────┘
               │  TRUST BOUNDARY 4: Parsed sessions → Output
               ▼
        ┌──────┴──────────────────────────────────┐
        │                                         │
   ┌────▼────────┐  ┌──────────────┐  ┌──────────▼──────┐
   │  Dashboard  │  │  Reports /   │  │  Org sync →     │
   │  HTML       │  │  Invoices    │  │  org.db (SQLite) │
   │  (localhost)│  │  (Markdown)  │  │  (hub dir)      │
   └─────────────┘  └──────────────┘  └─────────────────┘
        │
   ┌────▼──────────────────────────────────┐
   │  Agent Loop (log_agent.py)            │
   │  Claude/OpenAI tool-use → LLM query  │
   │  base_url validated (H-2 fix)        │
   └───────────────────────────────────────┘
```

**Key observation on trust boundary 2:** The log file is an implicit trust boundary that the code treats as append-only but never enforces as such. Any process running as the user can freely prepend, overwrite, or inject lines into `ai-sessions.log`. The parse layer validates format but not origin.

**Key observation on trust boundary 3:** The git context enrichment (`infer_project`, `current_branch`) runs *after* the session is already written to the unattributed log, with the git subprocess pointing at the collector's CWD. If the CWD has been tampered with (e.g., a malicious `.git/config`), inferred attribution is incorrect. This is accepted risk in the local threat model but worth documenting.

### 2.2 Authentication and Authorization Model

Halyard has **no authentication or authorization model** — by design. This is the right choice for a local-first, single-user application. The consequences are:

- Any process running as the user has full read/write access to all Halyard data
- The dashboard HTTP server (binding 127.0.0.1) enforces no identity beyond "same-machine process" for no-Origin requests
- The org sync layer adds email-based identity, but this identity is self-asserted from `AiSession.user` which is populated from git config or left empty — it is not verified

This is acceptable within the stated threat model. It becomes a gap when Halyard is used in shared environments (CI agents, shared developer VMs, NFS home directories, containers). The absence of authorization is not documented as a known limitation in any user-facing file.

**Recommendation:** Add a security model note to the README or a `SECURITY.md` documenting: "Halyard assumes a single-user, trusted-OS environment. All data in `~/.halyard/` is user-accessible. Multi-user deployments should restrict `~/.halyard/` permissions accordingly."

### 2.3 Session Attribution Model: Design Analysis

Attribution of a session to a project follows a four-level priority cascade:

1. **Active timer file** (`~/.halyard/active`, `slug=` field): highest priority. Set by `halyard start` or the dashboard `/api/start` endpoint.
2. **Cursor workspace roots** (for Cursor collector only): `payload.workspace_roots[0]` used to walk up to `halyard.toml`.
3. **Git remote inference** (`infer_project(cwd)`): maps git origin URL → project slug via `~/.halyard/repos.toml` or auto-derives `git/<repo-name>`.
4. **Interactive backfill**: `halyard assign-unattributed` or `halyard confirm-attribution`.

**Trust levels across this cascade are unequal but unmarked.** Level 1 attribution (active timer) is user-confirmed. Level 3 attribution (git inference) is a heuristic. Both produce a `project=` KV in the log that looks identical at parse time. The `attribution_state` field in `OrgSession` distinguishes "confirmed" from "inferred", but this distinction is not preserved in the local `ai-sessions.log` format — a limitation that makes audit reconstruction ambiguous.

**Specific attribution design gap — the active timer file is a shared state channel (D-2):**

Three collectors all read `~/.halyard/active` via `_read_active_project()`. Each implements this function independently with identical logic (`for line in active.read_text().splitlines(): if line.startswith("slug="): return line[5:]`). This is correct behavior but creates three independent readers with no locking. The active timer is set non-atomically by `dashboard.py` (`_HALYARD_ACTIVE.write_text(...)`, no temp-rename pattern). If a timer start races with a collector hook:

1. Collector reads `active` → gets stale or partial content → attributes to wrong project
2. Dashboard writes `active` → operation completes

This is not a security exploit in the traditional sense — it doesn't allow privilege escalation. But for a billing/invoicing application, incorrect attribution is a financial integrity issue. A session worth $5 attributed to client A instead of client B is a real error.

**Files:** `src/halyard/dashboard.py` line 111-114, `src/halyard/collectors/claude_code.py` line 143-149, `src/halyard/collectors/cursor.py` line 157-163, `src/halyard/collectors/gemini_cli.py` line 258-265.

### 2.4 Org Identity Model: Design Analysis

The org sync pathway introduces a second identity layer on top of the single-user attribution model:

```
AiSession.user (git email, optional)
    → org.toml member list lookup
        → OrgSession.team_id / user_id
            → org.db INSERT
                → Finance reports
```

**Critical weakness:** `AiSession.user` is populated from one source: the Cursor hook payload's `user_email` field (if present), or left as `None` for all other collectors. Claude Code and Gemini sessions carry no user email from the hook layer. For these sessions, `normalize_session()` calls `org_config.resolve_user("")` which returns `("", "(unassigned)")`.

This means in a multi-user org setup using Claude Code:
- All Claude Code sessions in the org store will have `user_id = ""` and `team_id = "(unassigned)"`
- Finance rollups will show these as unassigned
- Per-developer cost tracking is effectively impossible for Claude Code users unless they manually add `user=` to every session via backfill

This is a **design gap in the multi-user identity model**, not a security vulnerability per se, but it means the org reports cannot be relied upon for per-person attribution with Claude Code as the primary tool.

**Source:** `src/halyard/collectors/cursor.py` (no `user_email` extraction visible — the payload comment mentions it as a Cursor-specific field but the code doesn't actually capture it), `src/halyard/org.py` line 194.

### 2.5 Implicit Security Assumptions

The following assumptions are embedded in the code but not documented anywhere in the codebase. They are valid within the stated threat model but represent brittle foundations:

| Assumption | Where relied upon | What breaks if false |
|---|---|---|
| `ai-sessions.log` is append-only and never truncated | `parse_sessions()` reads entire file each call; no hash chain | Log replay attack: an attacker replacing lines would go undetected |
| TOML config files are writable only by the current user | All of `halyard.toml`, `clients.toml`, `projects.toml`, `org.toml` | Privilege escalation via config injection on shared machines |
| `~/.halyard/active` contains content written only by `halyard start/stop` | All three collectors read `slug=` line directly | Attribution manipulation by writing to the active file |
| Timeclock append mode is atomic at the OS level | `dashboard.py` lines 109-110 and 121-123 | Race condition on Windows or NFS mounts causing interleaved writes |
| Jinja2 template `invoice.md.j2` is not user-writable | `_render_invoice()` uses `autoescape=False` | If template directory is writable by another process, arbitrary content injection into invoices |
| Gemini history files at `~/.gemini/tmp/*/chats/session-*.json` are written only by the Gemini CLI | `gemini_history.py` parses these with full trust | Any process can write a fake history file to manipulate cost data |
| `~/.halyard/pricing.toml` is written only by `halyard update-pricing` | Used as an override for all cost calculations | A process that can write this file can modify all future cost calculations |
| `~/.halyard/hub` contains a valid Halyard project path | Trusted as a directory path without canonicalization | Symlink attack pointing hub at an attacker-controlled directory |

---

## 3. Design-Level Findings

### 3.1 D-1: Session Attribution Audit Gap

**Severity:** High (financial integrity)  
**Type:** Design pattern  
**Not covered by Adrian's scan**

**Description:**

The session log format records `project=<slug>` as a space-delimited KV field, written by the collector at capture time or added by backfill operations. The log provides no record of *how* the attribution was assigned — whether from the active timer (user-confirmed), git inference (heuristic), workspace root (Cursor-specific), or manual backfill. All attributions look identical:

```
s 2026-05-06T10:30:00 2026-05-06T11:15:00 claude-code claude-sonnet-4-6 10000 2000 0.0600 project=acme:auth
```

**Why this matters for a billing application:**

When a client questions an invoice, the billing business must be able to demonstrate that the sessions billed were actually worked on their project. The current log format does not support this. There is no way to distinguish:
- A session where the user had started an active timer for `acme:auth` (strong evidence)
- A session where git inferred `acme:auth` from the remote URL (circumstantial)
- A session that was backfilled to `acme:auth` three days later by `halyard assign-unattributed` (weakest)

The `OrgSession.attribution_state` field in `org.py` distinguishes "confirmed" from "inferred", but this is computed from `any(t == "attribution:inferred" for t in tags)` — meaning it is only set for sessions that had an `attribution:inferred` tag. The current codebase never writes an `attribution:inferred` tag anywhere. The distinction is in the schema but dead in practice.

**Specific code references:**
- `src/halyard/ai_log.py` lines 165-187 (`assign_unattributed_sessions`): appends `project=<slug>` with no attribution source marker
- `src/halyard/orchestration.py` lines 202-203: `append_session(target_dir, replace(session, project=target_project))` — same issue
- `src/halyard/org.py` lines 197-200: `attribution_state` computed from an `attribution:inferred` tag that no collector sets

**Recommendation:**

Add an `attr_method=` KV field to the log line encoding, with values: `timer` (active timer was running), `ws_root` (Cursor workspace root), `git` (git inference), `backfill` (manual backfill), `manual` (explicit CLI flag). This is a backward-compatible addition to the log format — old parsers will silently ignore the unknown KV. Update the `_is_assignable_session_line` check accordingly. Surface this field in the `OrgSession` schema and include it in the finance export.

---

### 3.2 D-2: Active Timer File — Race Condition and Integrity Gap

**Severity:** High (financial integrity)  
**Type:** File I/O design + shared state  
**Not covered by Adrian's scan**

**Description:**

`~/.halyard/active` is a plain-text key-value file used as shared state between the dashboard and all three collectors. It is written non-atomically:

```python
# dashboard.py lines 111-114
_HALYARD_ACTIVE.write_text(
    f"timeclock={timeclock}\nslug={account}\nstarted={ts}\n"
)
```

`write_text()` is not atomic — it opens, truncates, and writes. A collector that reads the file during the truncation window will see empty content and return `None` for the active project, attributing the session to `git/<repo>` or the unattributed log instead.

Three independent reimplementations of `_read_active_project()` exist in the three collectors (identical logic, separate code). If the logic were ever changed for one collector and not the others, attribution behaviour would diverge silently.

Additionally, the `active` file has no schema version, no timestamp of when it was written, and no validation beyond `line.startswith("slug=")`. Any process running as the user can write a `slug=evil:project` line and cause all three collectors to attribute sessions to `evil:project` until the timer is stopped.

**Specific code references:**
- `src/halyard/dashboard.py` line 112: non-atomic write
- `src/halyard/collectors/claude_code.py` lines 143-149
- `src/halyard/collectors/cursor.py` lines 157-163
- `src/halyard/collectors/gemini_cli.py` lines 258-265

**Recommendation:**

1. Move `_read_active_project()` to a shared location (e.g., `ai_log.py` or a new `state.py`) with a single implementation imported by all collectors.
2. Replace `write_text()` with the atomic temp-rename pattern already used elsewhere:
   ```python
   tmp = _HALYARD_ACTIVE.with_suffix(".tmp")
   tmp.write_text(content)
   tmp.replace(_HALYARD_ACTIVE)
   ```
3. Consider adding an `active_pid=` field to detect stale active files from crashed processes.

---

### 3.3 D-3: Org Identity and `org.toml` Integrity

**Severity:** Medium  
**Type:** Authorization design  
**Not covered by Adrian's scan**

**Description:**

`org.toml` is the authoritative source for team membership mapping in the org sync path. The sync pipeline at `sync.py` reads `org.toml`, then maps every session in the local `ai-sessions.log` to a team and user identity. The result is inserted into `org.db` (SQLite) at the hub directory.

There is no integrity check on `org.toml`. Any contributor with write access to the hub directory can:
1. Add themselves to a different team to re-classify their cost attribution
2. Add another user's email to their team to claim their cost data
3. Remove a member entry to suppress their sessions from all future rollups (sessions become `(unassigned)`)
4. Change the `org.id` to cause all sync operations to produce orphaned records under a different org namespace

The `sync_audit` table in `org.db` records who synced and when, but not what `org.toml` looked like at sync time. If `org.toml` is silently modified between syncs, there is no way to detect the change in retrospect.

**Specific code references:**
- `src/halyard/org.py` lines 98-109: `read_org_config()` — reads and trusts `org.toml` entirely
- `src/halyard/sync.py` lines 39-40: no hash comparison, no version check
- `src/halyard/org_store.py` lines 149-167: `record_sync()` — does not record `org.toml` hash

**Recommendation:**

1. At sync time, compute a SHA-256 of the `org.toml` content and store it in the `sync_audit` row (add an `org_toml_hash` column).
2. Warn or require explicit confirmation if the `org.toml` hash differs between two consecutive syncs.
3. Long-term: document `org.toml` as a file that should be version-controlled (git-tracked) at the hub, which provides change history and attribution.

---

### 3.4 D-4: Remote Pricing Table — Authenticated Fetch Absent

**Severity:** Medium  
**Type:** Supply chain / data integrity  
**Not covered by Adrian's scan (L-4 touched dependency versions, not data integrity)**

**Description:**

`pricing.py` fetches the remote pricing table from:
```python
_REMOTE_URL = "https://raw.githubusercontent.com/Kormiloio/Halyard/main/pricing/models.toml"
```

The fetch uses Python's `urllib.request.urlopen` with the system trust store, which provides TLS certificate validation — that is, the connection to `raw.githubusercontent.com` is encrypted and the certificate is verified. However:

1. **No content hash pinning.** There is no mechanism to verify that the fetched content matches an expected hash. If the GitHub repository is compromised, or if the raw URL is served from a CDN that has been tampered with, a malicious pricing table will pass all existing validation.

2. **No last-fetched-from record.** The cached `~/.halyard/pricing.toml` contains no metadata about when or from where it was fetched. If someone overwrites it with a local file, `load_pricing_table()` will silently use the overwritten values.

3. **Global process-level cache.** `_merged_table` is a module-level singleton, reset only on `update_pricing()` calls. A process that starts before a manual pricing update uses stale prices for its entire lifetime.

4. **Pricing staleness is advisory, not enforced at invoice generation.** `pricing_table_age_days()` is called by `check_pricing_staleness()` and surfaced in doctor/health checks, but invoice generation in `invoicing.py` calls `parse_sessions()` which calls `calculate_cost()` which calls `load_pricing_table()` — none of these abort or warn if the pricing table is stale or absent.

**Consequence:** An invoice generated after a pricing table compromise would bill the client at incorrect rates with no warning in the invoice itself.

**Specific code references:**
- `src/halyard/pricing.py` lines 137-208: `update_pricing()` — validates structure, not provenance
- `src/halyard/pricing.py` lines 211-237: `calculate_cost()` — silent fallback to 0.0 for unknown models
- `src/halyard/invoicing.py` lines 489-502: `_ai_cost_for()` — no staleness check before summing costs

**Recommendation:**

1. Add a `sha256=` comment field to `pricing.toml` that records the SHA-256 of the content at fetch time. Verify on load.
2. Emit a `[halyard] WARNING: pricing table is N days old` to stderr during invoice generation if the table is older than 30 days.
3. Consider publishing a signed manifest alongside the pricing table (even a simple detached `.sig` file) for users who require supply chain integrity.

---

### 3.5 D-5: Dashboard CSRF Guard — Local Process Blind Spot

**Severity:** Medium  
**Type:** Authorization design  
**Partially covered by Adrian (H-1) — this extends that finding**

**Description:**

The H-1 fix correctly guards against browser-based CSRF by checking the `Origin` header. The implementation explicitly allows requests with no `Origin` header:

```python
# dashboard.py lines 78-88
origin = self.headers.get("Origin", "")
if origin:
    # ... validate origin ...
    if origin not in allowed:
        self.send_error(HTTPStatus.FORBIDDEN, ...)
        return
# Falls through: no Origin header → proceed
```

This is correctly documented in the code comment ("Curl/CLI calls with no Origin header are still permitted"). However, the security implication is not documented anywhere in user-facing material: **any local process can freely start and stop the user's timeclock.** This includes:

- A malicious shell script sourced from an untrusted dotfile
- A compromised npm/pip package with a postinstall hook
- A cron job planted by another process running as the same user
- A Halyard hook (installed by `halyard install-hook`) that could be modified to call the dashboard

The `ThreadingHTTPServer` also processes requests concurrently (each request in its own thread). The timeclock append operations are atomic on POSIX (`open("a")` + single write), but the `_HALYARD_ACTIVE` file reads and writes within the same POST handler are not atomic with respect to concurrent requests. Two simultaneous `/api/start` calls could both see `read_active_timer()` return `None` and both write `i` entries.

**Specific code references:**
- `src/halyard/dashboard.py` lines 94-114: `/api/start` handler — checks `read_active_timer()` but the check and write are not atomic
- `src/halyard/dashboard.py` line 116-124: `/api/stop` — same pattern

**Recommendation:**

1. Add a comment in the `SECURITY.md` / README that explains the localhost-only CSRF model explicitly: "The dashboard POST endpoints require no secret beyond network access to 127.0.0.1. Any process running as the user can start or stop the timeclock."
2. Add a simple concurrency guard for timeclock mutation: check for an existing `i` entry before writing another `i` (the current check `not read_active_timer()` is correct logic but runs in a window before the write).
3. Consider adding rate limiting (e.g., reject more than one `/api/start` per 5 seconds) to reduce risk from script loops.

---

### 3.6 D-6: Log Format Round-Trip Fidelity — Underscore Ambiguity

**Severity:** Low  
**Type:** Data integrity / audit  
**Documented in M-2 remediation — this elevates it as a design-level issue**

**Description:**

The `note` and `resume_command` fields use space-to-underscore encoding. This is correctly documented in `ai_log.py` and verified by `test_note_with_underscores_ambiguity_documented`. However, the design implication is larger than a code comment:

**Every note containing underscores silently changes meaning after a write-read cycle.** A note written as `snake_case_note` is read back as `snake case note`. This is not merely a display issue — if session notes are used in organizational reports, governance dashboards, or exported data, the round-trip loss creates a semantic gap between what the user wrote and what the system records.

For a financial/audit-grade application, this encoding scheme is technically adequate but professionally fragile. A client auditing the billing records would see notes with unexpected spaces where underscores were intended.

The fix is straightforward: percent-encoding (`urllib.parse.quote`/`unquote`) is backward-compatible with the existing parser (the parser only splits on whitespace and `=`, not `%`), preserves all characters faithfully, and is widely understood.

**Specific code references:**
- `src/halyard/ai_log.py` lines 111-118 (note encoding) and 284-285 (note decoding)
- `src/halyard/ai_log.py` lines 136-140 (resume_command encoding) and 308-309 (decoding)

**Recommendation:** Add `_percent_encode(value: str) -> str` and `_percent_decode(value: str) -> str` helpers using `urllib.parse.quote(value, safe='')` / `urllib.parse.unquote(value)`. Apply to `note` and `resume_command` in a new log format version, with backward-compatible fallback for reading old underscore-encoded values (detect `%` in value → use `unquote`; else use `replace("_", " ")`).

---

### 3.7 D-7: Gemini History Parser Trust Model

**Severity:** Low  
**Type:** External data trust boundary  
**Not covered by Adrian's scan**

**Description:**

`gemini_history.py` reads session files from `~/.gemini/tmp/*/chats/session-*.json`. These files are written by the Gemini CLI, not by Halyard. The parser trusts:

- The `sessionId`, `model`, and token counts in these files are accurate
- The `codeStats.added` / `codeStats.linesAdded` fields reflect actual code changes
- The `toolCalls` array faithfully represents tool invocations

Unlike hook payloads (which come from a tool Halyard installs), Gemini history files are owned entirely by the Gemini CLI and could be modified by any process with write access to `~/.gemini/`. More subtly, future versions of the Gemini CLI could change the schema in ways that produce silent incorrect parsing (e.g., `candidatesTokenCount` becoming `outputTokenCount`).

`find_session_file()` uses a glob pattern `*/chats/session-*-{prefix}.json` where `prefix = session_id[:8]`. The first 8 characters of a session ID is a very short prefix. If two sessions share the same 8-character prefix (plausible with UUIDs if the collision space is large but finite), the function returns the most-recently-modified file, which may be the wrong session.

**Specific code references:**
- `src/halyard/collectors/gemini_history.py` lines 156-166: `find_session_file()` — prefix collision risk
- `src/halyard/collectors/gemini_history.py` lines 74-153: `parse_session_file()` — full trust in file content

**Recommendation:**

1. Use the full session ID for file matching, not just the first 8 characters. If the filename convention guarantees uniqueness, use it fully.
2. Add a schema version check: if the history file contains neither `candidatesTokenCount` nor `outputTokenCount`, log a warning rather than silently returning 0 output tokens.
3. Document the Gemini history trust model: "These files are written by the Gemini CLI and trusted as-is. Cost data from Gemini sessions may be incorrect if the history files are modified."

---

### 3.8 D-8: Codex Imported-State File — No Integrity Guarantee

**Severity:** Low  
**Type:** Deduplication state integrity  
**Not covered by Adrian's scan**

**Description:**

`codex_app.py` maintains a deduplication set in `~/.halyard/codex-imported` (one UUID per line). This file is read on every import run to avoid inserting duplicate sessions. The file is written with `_save_imported_state()` which overwrites the file entirely (not atomically).

If `_save_imported_state()` is interrupted mid-write (power loss, SIGKILL), the imported-state file is corrupted or empty. The next `halyard import-codex` run will re-import all previously imported sessions, creating duplicates in `ai-sessions.log`. There is no deduplication at the log level for Codex sessions (unlike the org store, which uses `local_log_line_hash` for idempotency).

**Specific code references:**
- `src/halyard/collectors/codex_app.py` lines 193-196: `_save_imported_state()` — `write_text()` is not atomic

**Recommendation:** Apply the atomic temp-rename pattern to `_save_imported_state()`:
```python
tmp = _IMPORTED_STATE_FILE.with_suffix(".tmp")
tmp.write_text("\n".join(sorted(ids)) + "\n")
tmp.replace(_IMPORTED_STATE_FILE)
```

---

### 3.9 D-9: `plist` Generation — XML Injection Surface (Structural Analysis)

**Severity:** Low  
**Type:** Injection (structural, not shell)  
**Not a re-statement of Adrian's observation — this is a new architectural angle**

**Description:**

Adrian noted that the plist XML embeds `project_dir` and `halyard_exe` inside `<string>` tags within `<array>` elements, and concluded this is safe. This is correct for shell injection. However, the `_plist()` function uses Python f-string interpolation to build raw XML:

```python
# service.py lines 61-86
def _plist(halyard_exe: str, project_dir: Path, port: int) -> str:
    return f"""...
        <string>{halyard_exe}</string>
        <string>dashboard</string>
        <string>--project-dir</string>
        <string>{project_dir}</string>
        ...
```

`halyard_exe` comes from `shutil.which("halyard")` — normally a filesystem path. `project_dir` is a `Path` object, cast via f-string to its string representation. Neither value is XML-escaped before interpolation.

If `project_dir` contains `<`, `>`, `&`, `"`, or `'` characters (possible on some filesystems or if the user names their project directory with such characters), the generated plist will be malformed XML that `launchctl` may reject or misparse. More critically, a `project_dir` of `/Users/alice/</string></array><key>EnvironmentVariables</key><dict><key>PATH</key><string>/malicious` would inject arbitrary plist keys into the LaunchAgent.

**Why this matters:** A LaunchAgent plist is executed as a persistent background service on macOS. Injecting arbitrary plist keys could set environment variables, change the run-at-load behavior, or modify the standard output path — giving an attacker (who already controls the project directory name) persistent process-level control.

This attack requires the user to name their Halyard project directory with XML special characters — which is unusual but not impossible, particularly if the project directory path is constructed programmatically (e.g., from a git clone of a specially-named repository).

**Specific code reference:**
- `src/halyard/service.py` lines 60-86: `_plist()` — no XML escaping applied

**Recommendation:**

```python
import xml.sax.saxutils

def _plist(halyard_exe: str, project_dir: Path, port: int) -> str:
    safe_exe = xml.sax.saxutils.escape(str(halyard_exe))
    safe_dir = xml.sax.saxutils.escape(str(project_dir))
    safe_log = xml.sax.saxutils.escape(str(LOG_PATH))
    return f"""...<string>{safe_exe}</string>...<string>{safe_dir}</string>..."""
```

`xml.sax.saxutils.escape()` handles `<`, `>`, and `&`. This is a low-effort, high-value defence-in-depth fix.

---

### 3.10 D-10: `budget.py` — Non-Atomic Config Write

**Severity:** Low  
**Type:** File I/O atomicity  
**Not covered by Adrian's scan**

**Description:**

`budget.py`'s `set_budget()` writes `~/.halyard/budgets.toml` non-atomically:

```python
# budget.py line 163
_BUDGETS_FILE.write_text(tomli_w.dumps(data))
```

If interrupted, `budgets.toml` is left empty or truncated, silently deleting all budget limits. On the next session start, `load_budgets()` returns `{}`, and no budget checks fire — meaning a user over their daily limit would not receive the budget warning. While this is a user safety issue rather than a security issue, it represents an inconsistency in the codebase: `assign_unattributed_sessions`, `backfill_window`, `confirm_session_attributions`, and `update_pricing` all use atomic temp-rename, but `set_budget` and `_write_invoice_counter` do not.

**Specific code references:**
- `src/halyard/budget.py` line 163: `set_budget()` — non-atomic write
- `src/halyard/invoicing.py` line 520: `_write_invoice_counter()` — `path.write_text(tomli_w.dumps(config))` — also non-atomic

**Recommendation:** Apply the atomic temp-rename pattern to both `set_budget()` and `_write_invoice_counter()`.

---

## 4. API Surface and Error Handling Assessment

### 4.1 Agent Tool Loop — Data Exposure Analysis

The `log_agent.py` tool dispatch (`_execute_tool`) returns `AiSession` objects serialized via `dataclasses.asdict()` to the LLM. This is a deliberate, well-considered design: the data returned includes `tool`, `model`, `project`, `cost_usd`, `input_tokens`, `output_tokens`, and session timestamps — all of which are necessary for the LLM to answer questions about work sessions.

**What is not exposed (correct):** API keys, file paths beyond project slugs, usernames beyond `user=` field (which is optional and empty by default), note content (included as the `note` field, which may contain user-written text).

**What is exposed that deserves attention:**

The `note` field is included in `asdict()` output and passed to the LLM. If users write sensitive information into session notes (client names, pricing details, internal project names), this data flows to the external Claude or OpenAI API. There is no filtering of `note` content before it reaches the LLM. For a tool explicitly designed to help users query their own data, this is the intended behavior — but it should be documented: "Session notes are sent to the AI provider when using --agent claude or --agent openai."

**The `limit` parameter DoS gap (from Adrian's scan, Domain 9) is architectural:**

```python
# log_agent.py line 494
limit = args.get("limit", 20)
return [asdict(s) for s in sessions[:limit]]
```

There is no server-side cap. An LLM that requests `limit=2000000` will cause `parse_sessions()` to read and serialize the entire log. For a local application with a modest log (hundreds to low thousands of sessions), this is a bounded-memory DoS with a practical ceiling. For a hub log that aggregates sessions across months of multi-tool use, this could be tens of thousands of sessions, each serialized to a large dict. At 10,000 sessions × ~500 bytes per dict, this is ~5MB in memory — uncomfortable but not catastrophic. The risk rises with log age.

**Recommendation:** Add `limit = min(int(args.get("limit", 20)), 500)` to cap at 500 sessions regardless of LLM request.

### 4.2 Dashboard HTML Generation — Edge Case Analysis

All values rendered into HTML pass through `_e()` → `html.escape()`. This is consistently applied across all 20+ HTML rendering functions. No XSS path was found.

One subtle edge case: `session.input_tokens:,` and `session.cost_usd:.4f` are formatted directly using Python format specifiers without escaping. These are numeric values from parsed log entries — `input_tokens` is validated as `int >= 0` and `cost_usd` as `float >= 0` by `_parse_line_result()`, so they cannot contain HTML-dangerous characters. This is safe but worth noting as a dependency on the parser validation.

### 4.3 Error Message Leakage — Post-Remediation Assessment

Both M-6 (Anthropic SDK errors) and the parallel OpenAI error handling have been fixed with the pattern:
```python
raise LogAgentError(f"Anthropic API error: {type(exc).__name__} — check your ANTHROPIC_API_KEY.") from exc
```

This is correct. One additional case to note: `load_log_config()` emits a Python `warnings.warn()` for an unknown `default_agent` value. `warnings.warn()` by default prints to stderr, which may be captured by shell scripts or CI logs. The message includes the invalid value: `f"unknown log.default_agent '{raw_agent}'"`. This is not a credential leak but could expose configuration details in log aggregation systems.

### 4.4 `sync.py` — Error String Contents

`sync_project()` at line 59 produces error strings of the form:
```python
result.errors.append(f"Normalization error for line '{raw[:60]}': {exc}")
```

`raw[:60]` is the first 60 characters of a raw log line. A log line looks like:
```
s 2026-05-06T10:30:00 2026-05-06T11:15:00 claude-code claude-sonnet-4-6 10000 2000 0.0600 project=acme:auth note=some_note
```

The first 60 characters would include timestamps, tool name, model name, and token counts — no credentials or personal data. The `note` field typically falls after position 60. This is safe but deserves a comment confirming the design intent.

---

## 5. Test Suite Security Assurance Matrix

The 39 test files contain a mix of behavioral tests and explicit security property tests. The following matrix assesses which security properties are tested, which are partially tested, and which have no test coverage.

### 5.1 Fully Tested Security Properties

| Security Property | Test File | Test Name(s) |
|---|---|---|
| M-1: `tool`/`model` newline injection blocked | `test_ai_log.py` | `test_newline_injection_tool_sanitized`, `test_newline_injection_model_sanitized`, `test_newline_injection_round_trips_safely` |
| M-1: `_safe_field` strips `=`, whitespace, caps at 128 | `test_ai_log.py` | `test_safe_field_strips_newline`, `test_safe_field_strips_equals`, `test_safe_field_caps_at_128_chars` |
| M-2: `note`/`resume_command` encoding round-trip | `test_ai_log.py` | `test_note_with_spaces_round_trips`, `test_resume_command_with_spaces_round_trips`, `test_note_with_underscores_ambiguity_documented` |
| M-3: Slug path traversal rejected in `_read_clients` | `test_invoicing.py` | `test_read_clients_rejects_traversal_slug`, `test_read_clients_rejects_slug_with_spaces` |
| M-3: Slug path traversal rejected in `_read_projects` | `test_invoicing.py` | `test_read_projects_rejects_traversal_slug`, `test_read_projects_rejects_traversal_client_slug` |
| M-4: Invoice path confined to invoices/ | `test_invoicing.py` | `test_generate_invoice_path_confined_to_invoices_dir` |
| M-5: Quarantine error newline injection blocked | `test_ai_log.py` | `test_quarantine_error_newline_escaped`, `test_quarantine_error_no_carriage_return` |
| L-3: Atomic write for `assign_unattributed_sessions` | `test_ai_log.py` | `test_assign_unattributed_sessions_atomic_write` |
| H-1: CSRF cross-origin POST rejected | `test_dashboard.py` | `test_csrf_rejects_cross_origin_post` |
| H-1: CSRF same-origin POST allowed | `test_dashboard.py` | `test_csrf_allows_same_origin_post` |
| H-1: No-Origin POST allowed (curl/CLI) | `test_dashboard.py` | `test_csrf_allows_no_origin_post` |
| H-2: `_validate_base_url` rejects non-HTTPS/non-localhost | `test_log_agent_openai.py` | `test_validate_base_url_rejects_plain_http_remote`, `test_validate_base_url_rejects_file_scheme`, `test_validate_base_url_rejects_data_scheme` |
| H-2: Malicious `base_url` blocked before network call | `test_log_agent_openai.py` | `test_run_openai_log_query_rejects_malicious_base_url` |
| Pricing: Non-positive price rejected | `test_pricing.py` | `test_update_pricing_validation_non_positive_price` |
| Pricing: Truncated response (< 3 models) rejected | `test_pricing.py` | `test_update_pricing_validation_too_few_models` |
| Pricing: Atomic write on update | `test_pricing.py` | `test_update_pricing_atomic_replaces_existing` |
| Org deduplication: duplicate sync is idempotent | `test_org.py` | `test_sync_project_idempotent`, `test_insert_duplicate_returns_false` |
| Org GDPR: purge deletes records and writes audit | `test_org.py` | `test_purge_user_deletes_records_and_logs_audit` |

### 5.2 Partially Tested Security Properties

| Security Property | Gap | Recommendation |
|---|---|---|
| Session log round-trip fidelity | `test_round_trip_all_optional_fields` tests most optional fields but not `model_breakdown`, `session_id`, `wall_seconds`, `agent_active_seconds`. Rich fields test (`test_rich_fields_round_trip`) covers these. **Complete.** | No action needed — coverage is adequate |
| Negative token validation | Tests `input_tokens=-1` quarantine. Does not test `output_tokens < 0` or `cost_usd < 0` quarantine paths. | Add `test_from_log_line_negative_output_tokens_quarantines` and `test_from_log_line_negative_cost_quarantines` |
| Slug validation accepts edge cases | Tests reject `../../evil` and `bad slug`. Does not test slugs at exactly 64 chars (boundary), slugs starting with `-`, slugs with uppercase. | Add boundary and edge case tests for `_SLUG_RE` |
| `_validate_base_url` IPv6 loopback | `test_validate_base_url_accepts_ipv6_loopback` — present. But does not test `http://[::2]/v1` (non-loopback IPv6). | Add `test_validate_base_url_rejects_non_loopback_ipv6` |
| Budget file corruption recovery | `load_budgets()` returns `{}` on `TOMLDecodeError`. Not directly tested. | Add `test_load_budgets_corrupted_file_returns_empty` |
| `_read_model_from_settings` exception handling | Catches `Exception` broadly — tested implicitly by `test_v1_collectors.py`. Not security-specific. | Low priority |

### 5.3 Security Properties with No Test Coverage

These are the critical gaps — security properties that the code claims to enforce but no test validates:

| Security Property | Location | Why it matters | Recommended Test |
|---|---|---|---|
| **Active timer file write atomicity** | `dashboard.py` lines 111-114 | Non-atomic write can corrupt attribution | Test that a concurrent start request does not produce a partially-written `active` file |
| **Plist XML injection** | `service.py` `_plist()` | A project_dir with `<` chars creates malformed XML | `test_plist_xml_special_chars_are_escaped()` — pass a `project_dir` containing `<>&` and assert the output parses as valid XML |
| **Codex deduplication atomicity** | `codex_app.py` `_save_imported_state()` | Non-atomic write can cause duplicate imports | `test_save_imported_state_atomic()` — confirm no `.tmp` file remains after successful write |
| **Budget file write atomicity** | `budget.py` `set_budget()` | Non-atomic write can delete all budget limits | `test_set_budget_atomic_write()` |
| **Gemini session file prefix collision** | `gemini_history.py` `find_session_file()` | Two sessions with matching 8-char prefix return wrong file | `test_find_session_file_collision_returns_most_recent()` |
| **Dashboard double-start prevention** | `dashboard.py` lines 100-102 | `not read_active_timer()` check is raceable | `test_dashboard_start_idempotent_under_concurrent_posts()` |
| **`org.toml` with malformed member entries** | `org.py` `read_org_config()` | Pydantic validation may raise on malformed TOML | `test_read_org_config_malformed_member_is_skipped()` |
| **Quarantine file is readable (not world-writable)** | `ai_log.py` `_write_quarantine()` | `path.open("a")` uses default umask — worth asserting | `test_quarantine_file_permissions_are_restrictive()` |
| **Hub path is validated as a directory** | `hub.py` `find_hub()` line 43 | `path if path.is_dir() else None` — but no canonicalization | `test_find_hub_symlink_followed_safely()` |
| **Session notes not stripped before LLM call** | `log_agent.py` `_execute_tool()` | Notes flow to external API — by design, but untested | `test_execute_tool_read_sessions_includes_note_field()` to document intent |

### 5.4 Test Infrastructure Assessment

**Test isolation:** All tests use `tmp_path` (pytest fixture) for file system operations. `monkeypatch.setattr(Path, "home", lambda: tmp_path)` is consistently used to redirect `~/.halyard/` operations. No tests write to the real `~/.halyard/`. This is correct and thorough.

**Mock fidelity:** The Claude and OpenAI agent loop tests use `unittest.mock.MagicMock` with realistic response structures. The mock payloads are structurally valid but do not include adversarial content (tool names not in the allowlist, malformed JSON in tool arguments, etc.). No tests exercise the `{"error": "Unknown tool: X"}` path in `_execute_tool()`.

**Concurrency:** No tests exercise concurrent behavior. The `ThreadingHTTPServer` is tested with single sequential requests. The race conditions described in D-2 and D-5 are structurally untestable with the current test helpers — they would require thread-safe coordination in the test harness.

**Real server tests:** `test_csrf_rejects_cross_origin_post` and adjacent tests spin up a real `ThreadingHTTPServer` on a random port. This is the correct approach — it validates the actual HTTP stack, not just the handler logic. The test helper `_make_request()` is well-structured and reusable.

---

## 6. Dependency and Supply Chain Assessment

### 6.1 Critical Dependency Risk Summary

| Package | Min Version | Security Surface | Risk Level |
|---|---|---|---|
| `anthropic>=0.40` | 0.40 | API key transmission, SDK error messages | Low — M-6 remediation sanitizes errors; key not stored |
| `jinja2>=3.1` | 3.1 | Invoice template rendering | Low — `autoescape=False` is documented; templates are bundled, not user-written |
| `pydantic>=2.6` | 2.6 | `OrgConfig` parsing, `OrgSession` validation | Low — Pydantic v2 has improved coercion behavior; strict types used |
| `tomli_w>=1.0` | 1.0 | Writing `halyard.toml`, `budgets.toml`, `repos.toml` | Low — output-only; no injection surface |
| `dateparser>=1.2` | 1.2 | Not found in core paths — may be a transitive dependency | Low — if not used directly, risk is contained |
| `typer>=0.12` | 0.12 | CLI argument parsing | Low — type-safe, no shell interpolation of arguments |
| `textual>=0.60` | 0.60 | TUI application | Low — rendering only |
| `watchfiles>=0.21` | 0.21 | File watching | Low — read-only, no code execution |

**`dateparser` usage note:** Searching the source code, `dateparser` does not appear to be imported in any source file. It may be a leftover dependency from a previous feature. If unused, it should be removed to reduce supply chain surface.

### 6.2 Hook Installation Security

`halyard install-hook` writes to Claude Code's `settings.json` at `.claude/settings.json` or `~/.claude/settings.json`. The hook entries are:

```json
"hooks": {
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "halyard cc-session"}]}],
  "Stop": [{"hooks": [{"type": "command", "command": "halyard cc-hook"}]}]
}
```

The commands `halyard cc-session` and `halyard cc-hook` are invoked by Claude Code on every prompt and every session stop. This is a persistent privilege: any process that replaces the `halyard` binary (e.g., by manipulating `PATH` before `halyard install-hook` runs, or by writing a malicious file earlier in the PATH) would have those hook commands executed inside Claude Code's environment on every prompt.

This is an inherent property of hook-based integrations and is not unique to Halyard — but it means users should be advised to verify `which halyard` after installation.

**Hook payload size:** There is no size limit on hook payloads read via `sys.stdin.read()`. A malicious tool could send a multi-megabyte JSON payload. `sys.stdin.read()` reads until EOF, buffering all of it in memory before `json.loads()` is called. For a CLI tool invoked by Claude Code, the memory limit is the process's available RAM. This is a theoretical OOM risk, not a practical one in the current threat model.

### 6.3 Lock File Recommendation

Adrian's L-4 finding recommended adding upper bounds on the highest-risk packages. The more important supply chain measure is establishing a development lockfile:

```
pip-compile --generate-hashes pyproject.toml -o requirements.lock
```

This should be committed to the repository and used in CI. The lock file provides reproducible builds, hash-verified downloads, and a clear record of what versions are in production.

---

## 7. Threat Model Boundaries: Where Assumptions Break

### 7.1 Multi-User / Shared Machine Deployment

Halyard is explicitly designed for single-user use, but the hub model (`halyard init --hub`) creates a shared log aggregation point. If the hub directory is on a shared filesystem (e.g., a team NFS mount), the threat model breaks in several ways:

- Multiple users can write to `~/.halyard/active` (if home directories are shared or symlinked)
- `ai-sessions.log` on NFS has no guaranteed atomic append behavior
- `org.db` (SQLite) is not safe for concurrent writes from multiple machines — SQLite WAL mode is needed, and network filesystem locking is unreliable

**This scenario is not documented as unsupported.** The hub feature description at the top of `hub.py` makes no mention of filesystem or concurrency requirements.

**Recommendation for Minerva:** Escalate to the product team: should the hub model be explicitly restricted to local-only filesystems? If multi-machine sync is a product goal, the org store (SQLite) needs WAL mode and the log format needs a more robust concurrency model.

### 7.2 CI/CD and Container Deployments

If Halyard hooks are installed in a CI environment (e.g., a developer using Claude Code in GitHub Codespaces or a shared dev container), the hook payload includes `workspace_roots` from the container's filesystem. Session attribution would use the container's git remote, which is correct. But:

- `~/.halyard/` in a container is ephemeral — sessions are lost between container restarts unless the volume is mounted
- The hub pointer (`~/.halyard/hub`) would point to a path that may not exist on restart
- Multiple CI jobs running in parallel could write to the same hub if home directories are shared via volume

These are operational gaps, not security vulnerabilities in the traditional sense — but they represent failure modes that produce silent data loss.

### 7.3 Windows Deployment

The codebase contains `if _sys.platform == "darwin"` checks in `service.py` (LaunchAgent) and `invoicing.py` (`_open_file`). The Windows `os.startfile()` path exists. However:

- File append mode (`open("a")`) on Windows is **not** atomic for single-line writes the way it is on POSIX. Windows does not support atomic append at the OS level without explicit locking
- `os.replace()` (used in atomic writes) is atomic on Windows but has different behavior if the target is open by another process (raises `PermissionError` instead of replacing atomically)
- Path separators: the code consistently uses `pathlib.Path` which handles this correctly, but `str(project_dir)` in the plist generator would produce backslashes on Windows, which would be wrong in an XML plist context

Windows support appears to be a secondary concern, but the `_open_file` Windows path suggests it is intended. If Windows is a target platform, the atomicity assumptions need platform-specific review.

---

## 8. Prioritized Recommendations

The following recommendations are ranked by risk and effort. Each is tagged with the responsible team.

### Tier 1: Address Within One Sprint (Design Integrity)

| # | Finding | Action | Owner |
|---|---|---|---|
| R-1 | D-9: Plist XML injection | Add `xml.sax.saxutils.escape()` to `_plist()` for `halyard_exe`, `project_dir`, and `LOG_PATH` | Kai (dev) |
| R-2 | D-2: Active timer non-atomic write | Replace `_HALYARD_ACTIVE.write_text()` with atomic temp-rename in `dashboard.py` | Kai (dev) |
| R-3 | D-8: Codex deduplication non-atomic write | Apply temp-rename to `_save_imported_state()` in `codex_app.py` | Kai (dev) |
| R-4 | D-10: Budget and counter non-atomic writes | Apply temp-rename to `set_budget()` and `_write_invoice_counter()` | Kai (dev) |
| R-5 | 4.1: Agent loop `limit` cap | Add `limit = min(int(args.get("limit", 20)), 500)` in `_execute_tool()` | Kai (dev) |

### Tier 2: Address in Next Milestone (Architecture Quality)

| # | Finding | Action | Owner |
|---|---|---|---|
| R-6 | D-2: Shared `_read_active_project()` | Consolidate three identical implementations into a single function in `ai_log.py` | Kai (dev) |
| R-7 | D-1: Attribution source marker | Add `attr_method=` KV to log line encoding for backfill and hook attribution | Product + Kai |
| R-8 | D-3: `org.toml` hash in sync audit | Add `org_toml_hash` column to `sync_audit`; compute and store SHA-256 at each sync | Kai (dev) |
| R-9 | D-6: Note/resume_command encoding | Replace underscore encoding with percent-encoding; backward-compatible read path | Kai (dev) |
| R-10 | D-4: Pricing staleness warning at invoice time | Emit `[halyard] WARNING: pricing table is N days old` in `_ai_cost_for()` | Kai (dev) |

### Tier 3: Documentation and Test Coverage (Quality)

| # | Finding | Action | Owner |
|---|---|---|---|
| R-11 | 5.3: Missing plist XML test | Add `test_plist_xml_special_chars_are_escaped()` | Nora (QA) |
| R-12 | 5.3: Missing budget atomicity test | Add `test_set_budget_atomic_write()` | Nora (QA) |
| R-13 | 5.3: Missing codex deduplication atomicity test | Add `test_save_imported_state_atomic()` | Nora (QA) |
| R-14 | 2.2: Security model documentation | Add `SECURITY.md` or README section documenting single-user trust model | Product |
| R-15 | D-7: Gemini history trust documentation | Add comment in `gemini_history.py` documenting trust assumptions | Kai (dev) |
| R-16 | 6.2: `dateparser` dependency audit | Confirm whether `dateparser` is actually used; remove if not | Kai (dev) |
| R-17 | 6.3: Add lock file to CI | Add `pip-compile --generate-hashes` to CI pipeline | Kai (dev) |

### Tier 4: Escalate to Minerva (Product Decisions Required)

| # | Finding | Decision needed |
|---|---|---|
| R-18 | 7.1: Hub on shared/NFS filesystems | Is multi-machine hub a supported deployment? If so, SQLite WAL mode and locking guidance needed |
| R-19 | D-3: `org.toml` write authorization | Should `org.toml` be read-only at the hub except via a Halyard CLI command that validates and logs changes? |
| R-20 | D-4: Pricing table hash pinning | Is supply chain integrity for the pricing table a product requirement? If so, a signed manifest is warranted |

---

## 9. Appendix A: Data Flow Critical Path Analysis

### A.1 Session Write Critical Path (Claude Code)

```
1. Claude Code fires Stop hook
2. claude_code.handle_stop_hook() reads stdin → json.loads()
3. Reads ~/.halyard/cc-session for start timestamp
4. Reads ~/.halyard/active for active project slug [UNGUARDED READ]
5. Calls git_context.infer_project(cwd) [GIT SUBPROCESS, cwd from CWD]
6. Creates AiSession object (model/tool sanitized via _safe_field)
7. Calls append_session(project_dir, session) OR write_unattributed_session(session)
8. append_session opens log in mode "a", writes to_log_line() + "\n"
```

Critical observations:
- Step 4: The active timer read (step 4) and the log write (step 8) are not atomic with respect to each other. A timer stop between steps 4 and 8 would result in a session attributed to a project that was no longer active.
- Step 5: The git subprocess uses `cwd` from `Path.cwd()` — the actual working directory of the Claude Code process. This is trusted implicitly.
- Step 8: POSIX O_APPEND semantics make individual `write()` calls atomic, but a session line is written as a single `f.write(line + "\n")` call. The newline is part of the single write — safe.

### A.2 Invoice Generation Critical Path

```
1. halyard invoice <client> --period YYYY-MM
2. _read_clients(project_dir) → validates slug via _SLUG_RE
3. _read_projects(project_dir) → validates slug via _SLUG_RE
4. _read_time_entries(time.timeclock) → parses timeclock
5. invoice_path = invoice_dir / f"{invoice_number}-{client_slug}.md"
6. invoice_path.resolve().is_relative_to(invoice_dir.resolve()) → containment check
7. _render_invoice() → Jinja2 with autoescape=False
8. invoice_path.write_text(rendered) [NOT ATOMIC]
9. _write_invoice_counter() → writes halyard.toml [NOT ATOMIC]
```

Both steps 8 and 9 are non-atomic. If the process is interrupted between step 8 and step 9, the invoice file exists but the counter was not incremented. The next `halyard invoice` call would try to create the same filename (already exists) and fail with "Invoice already exists: ... Use --force to overwrite." This is a UX issue, not a security issue.

---

## 10. Appendix B: Threat Tree Summary

### Attacker: Local process running as the same user

**Goal: Inflate cost reports to justify fictitious billing**

```
Inflate cost reports
├── Write fake sessions to ai-sessions.log directly
│   └── Feasible — no integrity check on log file
│       ├── Token counts bounded by parse validation (no negative values)
│       └── Cost values accepted as any non-negative float → unbounded
├── Modify ~/.halyard/pricing.toml to inflate rates
│   └── Feasible — any local process can write this file
│       └── All future cost calculations use the modified rates
├── Replace ~/.halyard/active to mis-attribute sessions
│   └── Feasible — file is written non-atomically, no MAC
│       └── Sessions during active window attributed to any project
└── Modify org.toml to re-assign team/user attributions
    └── Feasible — no integrity check, no write audit
```

**Goal: Corrupt audit trail without detection**

```
Corrupt audit trail
├── Truncate ai-sessions.log (remove sessions from log)
│   └── Feasible — no append-only enforcement, no hash chain
│       └── Sessions disappear from all reports; quarantine not triggered
├── Inject malformed lines to create quarantine noise
│   └── Partially mitigated: quarantine writes are sanitized (M-5 fix)
│       └── But quarantine.log is readable/writable by same user
└── Re-order log lines (e.g., move attributed sessions before backfill)
    └── Feasible — no timestamp ordering enforcement in parser
```

**Key finding from threat tree:** The log file has no cryptographic integrity protection. It is a plain text file writable by any process running as the user. This is acceptable for a single-user, trusted-OS application where the user is also the attacker (self-defeating). It becomes a real risk in shared environments (CI, shared VMs, contractor machines).

---

## 11. Appendix C: Scope Limitations and Out-of-Scope Items

The following were explicitly excluded from this review:

1. **Live exploitation / dynamic testing:** No fuzzing, no HTTP probing of a running server, no injection attempt against a live session.
2. **Dependency CVE scanning:** No `pip-audit` or `safety` run was performed. The risk summary in Section 6 is based on code analysis, not live CVE databases.
3. **CI/CD pipeline security:** GitHub Actions configuration, release signing, package distribution security are out of scope.
4. **Cryptographic primitives review:** The SHA-256 usage in `OrgSession.local_log_line_hash` and `schedule.py`'s `_session_uid` (SHA-1) were noted but not analyzed for collision resistance requirements.
5. **Penetration testing of the agent loop:** The Claude and OpenAI tool-use loops were analyzed statically. Dynamic testing with adversarial LLM responses (e.g., tool arguments designed to trigger path traversal, injection, or loop abuse) was not performed.
6. **Windows and NFS platform testing:** Noted as risk areas; not empirically tested.

---

## Sign-Off

**Reviewer:** Sage, Senior AppSec Engineer  
**Review completed:** 2026-05-08  
**Scope:** Full architectural review of the Halyard repository — source tree (47 files), test suite (39 files), prior findings (Adrian's review, 2026-05-08)  
**Next review recommended:** After R-1 through R-5 (Tier 1) are implemented, before any multi-user hub deployment, and before v1.0 public release.

**Findings summary:**

| ID | Severity | Title |
|---|---|---|
| D-1 | High | Session attribution is a trust claim, not a verified fact |
| D-2 | High | Active timer file is a single-writer, unguarded state channel |
| D-3 | Medium | Org identity resolution has no integrity check on `org.toml` |
| D-4 | Medium | Remote pricing table is validated but not authenticated |
| D-5 | Medium | Dashboard CSRF guard has a local-process blind spot |
| D-6 | Low | Note/resume_command underscore encoding creates round-trip ambiguity |
| D-7 | Low | Gemini history parser trust model is undocumented |
| D-8 | Low | Codex imported-state file write is not atomic |
| D-9 | Low | Plist XML generation does not escape special characters |
| D-10 | Low | Budget and invoice counter writes are not atomic |
