# Design

## Stack

- **Language:** Python 3.11+ (Typer for CLI, Rich for terminal output)
- **Agent:** Anthropic SDK direct, single-turn tool-use loop
- **Models:** Pydantic v2 for config schemas
- **Templating:** Jinja2
- **PDF:** typst via subprocess (cleaner output than weasyprint, single binary)
- **Time parsing:** dateparser
- **Tests:** pytest, with golden-file tests for invoice rendering

### Why Python?

Largest contributor pool for AI tooling, easy install via `pipx`, fast
iteration. We can rewrite hot paths or distribute as a Rust binary later
if real performance demands it. Day-one priority is contributor velocity,
not microbenchmark wins.

### Why typst over weasyprint?

typst produces consistently good-looking PDFs out of the box, compiles in
milliseconds, and has a clean templating language that we can expose to
power users later as an alternative invoice format. weasyprint requires
HTML+CSS to look professional, and the output quality varies. typst is a
single static binary the installer can fetch.

### Why no Beancount in v0?

Beancount makes the project look like an accounting tool, not a freelancer
tool. v0's audience is "freelancer who wants to log time and send invoices."
The double-entry ledger lands in v1 alongside expenses, which is when
double-entry actually pulls its weight.

## Agent loop

Single-turn tool-using loop, not multi-turn autonomy in v0.

A user message comes in. Claude is given the system prompt + the message +
the current tools. Claude either responds with text or proposes one or more
tool calls. Tool calls are executed (with approval for writes). The result
is fed back to Claude, which either calls more tools or produces a final
text response. Then we wait for the next user message.

We are explicitly NOT building an autonomous loop in v0. Every user
interaction is initiated by the user. No background work. No daemons.

### Tools exposed to Claude

```
read_text(path: str) -> str
    Read any file under the project root. No approval needed.

list_clients() -> list[Client]
    Read clients.toml and return parsed entries. No approval needed.

list_projects() -> list[Project]
    Read projects.toml and return parsed entries. No approval needed.

run_hledger(args: list[str]) -> str
    Run hledger with the project's time.timeclock as -f. Read-only.

append_timeclock(entries: list[TimeclockEntry]) -> None
    APPROVAL REQUIRED. Append timeclock entries to time.timeclock.

render_invoice(client_slug: str, period: Period, line_items: list[LineItem]) -> Path
    APPROVAL REQUIRED. Generate the invoice .md and .pdf, increment counter.

upsert_client(client: Client) -> None
    APPROVAL REQUIRED. Add or update a client in clients.toml.

upsert_project(project: Project) -> None
    APPROVAL REQUIRED. Add or update a project in projects.toml.
```

### Approval UX

When Claude proposes a write, the CLI:

1. Prints the human-readable diff (Rich-rendered).
2. Prompts: `Apply? [y/N/edit]` — `edit` opens `$EDITOR` on a temp file
   containing the proposed change so the user can tweak before applying.
3. On `y`, applies the change and returns success to the agent.
4. On `N`, returns a tool error like "User declined the change" so the
   agent can react conversationally.

## System prompt

Loaded from `prompts/system.md`, version-controlled in the repo. It
establishes:

- Halyard's role and constraints.
- The file layout and formats it can rely on.
- Formatting rules for timeclock entries.
- Escalation behavior (when in doubt, ask; never invent a slug).
- Tone (concise, direct, terminal-native).

## Out-of-scope clarification

No async, no daemons, no LSP, no extension points in v0. Each command is a
fresh process; state lives entirely in files. The only persistent runtime
state is `~/.halyard/active` (the active timer), which is a single line of
text.

## Testing strategy

- Unit tests for parsers (timeclock round-trip, TOML schema validation).
- Golden-file tests for the default invoice template — render a fixed input
  and diff against a checked-in expected output.
- A small integration test using Anthropic's prompt-caching test endpoint
  is **out of scope** for v0; we mock the agent layer in unit tests and
  exercise the real model only manually until v1.

## Open questions (resolve before implementation)

1. Default currency formatting: rely on Babel, or hard-code USD/EUR/GBP for v0?
2. typst install: bundle as a Python package dep, ship a small downloader
   script in `halyard init`, or instruct users to install separately?
3. API key handling: env var only (`ANTHROPIC_API_KEY`), or also a
   `~/.halyard/config.toml` entry? Env var only is simpler and safer.
