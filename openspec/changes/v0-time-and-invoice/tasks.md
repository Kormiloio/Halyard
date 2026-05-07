# Tasks

The implementation checklist for v0. Task IDs are referenced from the CLI
stub via `NotImplementedError("v0 task X.Y")` markers — when you implement a
task, update both the code and tick the box here.

## 1. Project skeleton

- [x] 1.1 Initialize Python package, pyproject.toml, ruff config
- [x] 1.2 Set up Typer CLI entry point with stub commands
- [ ] 1.3 Add CI: GitHub Actions running ruff + mypy + pytest on pushes/PRs
- [ ] 1.4 Reserve `halyard` on PyPI (publish a 0.0.1 placeholder)
- [ ] 1.5 Reserve a domain (halyard.dev or similar)

## 2. Data model

- [ ] 2.1 Pydantic models: `HalyardConfig`, `Client`, `Project`, `LineItem`,
       `TimeclockEntry`, `Invoice`
- [ ] 2.2 TOML readers/writers for `halyard.toml`, `clients.toml`,
       `projects.toml` (round-trip safe; preserves comments where possible)
- [x] 2.3 Implement `halyard init` — creates the full project layout from
       sensible defaults
- [x] 2.4 Preserve existing `.gitignore` contents during `halyard init`

## 3. Time tracking

- [x] 3.1 Implement `halyard start <slug>` and `halyard stop`, including the
       `~/.halyard/active` state file
- [ ] 3.2 Implement `halyard log <text>`: send to Claude, render the
       proposal, prompt for approval, append on confirm
- [ ] 3.3 dateparser integration for "this morning", "yesterday", "last
       Tuesday", etc., with a fixed reference timezone (the user's local)
- [ ] 3.4 Timeclock parser/writer with round-trip safety (formatting,
       comments)

## 4. Invoicing

- [ ] 4.1 Default Jinja invoice template — clean, professional, renders
       well at letter and A4
- [ ] 4.2 Implement `halyard invoice <client>` with `--month`, `--from`,
       `--to` flags
- [ ] 4.3 typst PDF rendering pipeline (subprocess; verify install on first
       run with a friendly error if missing)
- [ ] 4.4 Invoice number sequencing in `halyard.toml` per the spec scenarios
- [ ] 4.5 Open the PDF after generation using the platform-default viewer

## 5. Agent loop

- [ ] 5.1 Anthropic SDK integration + tool definitions (read_text,
       list_clients, list_projects, run_hledger, append_timeclock,
       render_invoice, upsert_client, upsert_project)
- [ ] 5.2 First version of `prompts/system.md`
- [ ] 5.3 Approval prompt UX (Rich-based diff renderer, y/N/edit flow)
- [ ] 5.4 Implement `halyard` (no args) REPL mode — readline history,
       slash commands (`/quit`, `/help`, `/model`)

## 6. Demo + launch

- [ ] 6.1 Record the 60-second demo video (this is the actual deliverable
       for v0 — the binary exists to make the video true)
- [ ] 6.2 README polish: animated GIF, install instructions, the pitch
- [ ] 6.3 Draft Show HN, Lobsters, /r/plaintextaccounting posts; sit on
       them until the demo is good
- [ ] 6.4 Tag and publish v0.1.0 on PyPI
- [ ] 6.5 Cross-post the demo video to X with the project pitch line
