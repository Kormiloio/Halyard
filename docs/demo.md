# Halyard — Demo Guide

This is the single source of truth for demoing Halyard. It covers two modes:

- **Live presentation** — you are at a keyboard with an audience watching.
  Follow Part 1 (the script). ~10 minutes.
- **Self-guided walkthrough** — someone exploring on their own. Jump to Part 2.
  ~5 minutes end-to-end.

Both use the same commands and produce the same output. The script just adds
the narration.

---

## Part 1 — Live Presentation Script

**Audience:** people with no technical background, or developers who have not
heard of Halyard.
**Format:** you talk, the terminal is on screen. Read the narration out loud.
Type the commands. The output speaks for itself.
**Time:** ~10 minutes.

### Opening (talk, no typing)

> "Let me start with a question. How many of you have used an AI tool — Claude,
> ChatGPT, Cursor, Gemini — to help with work in the last week?"

*(Pause for hands.)*

> "Now — do you know what that actually cost? Not just the subscription you pay
> each month — do you know which *project* it went toward, which model you used,
> how many tokens, what the real number was?"

*(Most people don't.)*

> "That gap is the problem. When engineers use AI tools to do work for clients,
> the AI costs real money — but there's been no way to track it by project.
> It disappears into a monthly subscription bill and nobody knows where it went.
> When it's time to bill the client, or report to a manager, or just ask
> 'is this AI spend actually producing anything?' — there's nothing to show.
>
> We built Halyard. It's an open AI work ledger. Every time you use an AI tool,
> Halyard writes down what happened — which tool, which model, how long, how much
> it cost, which project it belonged to — automatically, in plain text, on your
> own computer. No cloud required. No account. Just a log file you own.
>
> Let me show you."

---

### Part 1A — Setting up a project (2 min)

> "Imagine you're a freelancer. You have a client called Acme Corp. They've
> asked you to build an authentication system. You're using AI tools to move
> faster. Let's set Halyard up."

```bash
mkdir ~/demo-acme && cd ~/demo-acme
halyard init
```

> "That one command just created your project. Plain text files. Let's look."

```bash
ls
```

*Output shows: `halyard.toml`, `clients.toml`, `projects.toml`, `ai-plans.toml`*

> "No database. No cloud account. Everything lives right here. Let's tell
> Halyard about our client."

```bash
cat clients.toml
```

> "We fill this in with Acme's details and our hourly rate. And then the
> project — we tell Halyard it belongs to Acme and what we're building."

```bash
cat projects.toml
```

> "Now let's tell Halyard how we pay for AI tools. I use Claude — I pay $20 a
> month. I use Cursor — another $20. Halyard needs to know this so it can
> split those subscription costs across projects."

```bash
cat ai-plans.toml
```

---

### Part 1B — The magic: automatic capture (2 min)

> "Here's the part that surprises people. Once you install a hook — a tiny
> trigger that fires every time you use an AI tool — Halyard captures the
> session automatically. You don't do anything. You just work."

```bash
halyard install-hook
```

> "That just wired Halyard into Claude Code. Same thing exists for Cursor and
> Gemini. Now every AI session gets recorded. Let me show you what that looks
> like."

```bash
cat ai-sessions.log
```

*Show a few log lines. Point to one:*

> "See this line? That's one AI session. It says: started at 10:14, ended at
> 10:42, used Claude, model was claude-sonnet-4-6, 4,300 input tokens, 800 output
> tokens, cost 14 cents. Automatically written. Every single session.
>
> It's like a bank statement — but for AI work. And just like a bank statement,
> it's plain text. You can read it, search it, email it, put it in a
> spreadsheet. You own it. It's not locked in someone else's cloud."

---

### Part 1C — Tracking human time (1 min)

> "Halyard also tracks your regular work time. When you start working on a task:"

```bash
halyard start acme:auth
```

> "When you're done:"

```bash
halyard stop
```

> "That's it. Your human hours and your AI usage are now both tracked, tied to
> the same project."

---

### Part 1D — The report (2 min)

> "You've been working for a few weeks. AI sessions are piling up. Let's see
> where things stand."

```bash
halyard report
```

*Pause to let people read the output.*

> "This tells you everything. Human time: 3 hours 20 minutes this month. AI
> sessions: 14. AI cost: 73 cents from the API.
>
> But 73 cents doesn't tell the whole story — I also pay my Claude subscription.
> Halyard tracks that too."

```bash
halyard report --ledger
```

> "Now we see the real number: $44.93 in AI costs this month — that's the direct
> API cost plus the portion of my subscription that went to this project, broken
> down by project.
>
> Notice those labels — 'captured', 'allocated', 'mixed'. That's Halyard telling
> you how confident it is in each number. 'Captured' means we measured it
> directly from the API. 'Allocated' means it's an estimate from a subscription
> plan. Honest about the difference. Every time."

---

### Part 1E — The invoice (2 min)

> "End of month. Time to bill the client. Normally a freelancer would guess at
> how long things took. With Halyard:"

```bash
halyard invoice acme --period 2026-05 --include-ai-evidence
```

```bash
cat invoices/2026-05-001-acme.md
```

*Scroll to the AI evidence appendix.*

> "At the bottom there's an AI Usage Evidence section. 14 sessions, which
> tools, which models, exactly how many tokens, exactly what it cost. The client
> doesn't have to take your word for it. The log file is right there.
>
> It turns 'trust me, AI helped' into 'here are the receipts.' The next step is
> making this appendix cryptographically signed — so a client can verify the
> evidence came from the ledger without seeing any private prompts or source code."

---

### Part 1F — The live dashboard (2 min)

> "One more thing. If you want to watch your AI usage in real time:"

```bash
halyard tui
```

*Let it sit on screen for a moment.*

> "This updates live. Every time an AI session completes, it appears here.
> Sessions, costs, models — all updating as you work."

| Key | What it does |
|-----|--------------|
| `d` | Show only today's sessions |
| `w` | Show this week |
| `m` | Show this month |
| `a` | Show all time |
| `↑` `↓` | Navigate projects |
| `Enter` | Drill into a project |
| `Esc` | Go back |
| `b` | Filter by git branch |
| `p` | Toggle hub / project view |
| `?` | Open keyboard help |
| `q` | Quit |

*Press `?` to show the help modal. Press `m`, then arrow down and Enter to drill
into a project. Press `Esc`, then `q` to exit.*

---

---

### Part 1G — Honors and Friends of the Sea (2 min)

> "One more thing — Halyard rewards clean proof, not raw hours."

```bash
halyard honors
```

*Point at the rank and progress bar.*

> "Your rank advances on attributed sessions only — unattributed work doesn't
> count. Right now I'm a Deckhand. At fifty attributed sessions I become a
> Quartermaster. Reach a thousand across three projects and you're a Commodore.
>
> The stripes track your watch streak — consecutive days you opened and closed
> a timer. The medals reward specific behaviors: Eight Bells for your first
> completed watch, Clean Manifest for ending a day with nothing adrift, Fair
> Winds for seven consecutive clean days.
>
> The Passport at the bottom is one stamp per AI tool you've actually used.
> Claude Code, Cursor, Gemini — each tool gets a stamp the first time you
> capture a session from it."

```bash
halyard voyage
```

*Show the voyage roster if there are attributed sessions.*

> "And every project you work in gets a voyage. As sessions accumulate it
> moves through stages — Anchors Aweigh, Making Headway, Rounding the Mark,
> Flying Colors. When it hits your session budget or goes quiet for two weeks,
> it moors itself and earns a sea creature badge.
>
> The creature is personality-assigned: a big project with lots of sessions
> gets the Whale. A project that spanned three months gets the Sea Turtle. A
> tight, focused, fully-attributed delivery gets the Clownfish. You don't pick
> it — the log does."

---

### Closing (talk, no typing)

> "So what did we build?
>
> For a developer or freelancer: automatic AI session capture, human time
> tracking, cost allocation by project, and invoices with evidence attached.
>
> For a small AI shop: a shared habit of producing proof-of-work packets that
> make client conversations easier.
>
> For a company later: redacted rollups, governance, and finance reporting —
> without ever seeing what anyone actually typed into the AI.
>
> Everything is plain text. You own all of it. There's no Halyard account.
> No cloud. No vendor lock-in. If we disappear tomorrow, your files still
> work — they're just text files with a simple format. MIT licensed. Forever.
>
> That's Halyard."

---

### Q&A Reference

**"How does it know what model I used?"**
> The hook captures the response from the AI tool — it includes the model name
> and token counts. Halyard reads that data and writes it to your log.

**"What if I use a subscription like Claude for $20/month — does it know the
real cost?"**
> It can't know exactly because subscriptions don't charge per message. But it
> allocates the subscription cost proportionally across your sessions based on
> active time spent. It tells you it's an estimate — that's what the 'allocated'
> trust label means.

**"Does Halyard see my prompts? What I actually said to the AI?"**
> No. Never. It only captures metadata: timestamps, model, token counts, cost.
> The actual words you typed stay on your computer. That privacy boundary holds
> at every layer of the product.

**"Why plain text? Why not a database?"**
> Because you can read plain text in 10 years without any software. You can
> grep it, email it, put it in Excel. Databases get abandoned. Text files last
> forever. The log format is documented — anyone can write a parser in an
> afternoon.

**"Is this open source?"**
> Yes. MIT licensed. The collectors, the CLI, and the log format are all open.
> The code is on GitHub. If you want to see exactly what gets written to your
> log, you can read the source.

---

## Part 2 — Self-Guided Walkthrough

A complete setup from zero to first invoice. ~5 minutes.

### Prerequisites

```bash
pipx install halyard
```

### Step 1 — Initialize a project

```bash
mkdir ~/consulting/acme-auth && cd ~/consulting/acme-auth
halyard init
```

Edit `clients.toml` and `projects.toml`:

```toml
# clients.toml
[[client]]
slug = "acme"
name = "Acme Corp"
hourly_rate = 150
email = "billing@acme.example"
```

```toml
# projects.toml
[[project]]
slug = "auth"
client_slug = "acme"
name = "Auth migration"
```

### Step 2 — Configure AI plans

Edit `ai-plans.toml`:

```toml
[[plan]]
slug = "claude-max"
tool = "claude-code"
billing = "seat"
monthly_usd = 200
allocation = "active_minutes"
starts_on = "2026-01-01"

[[plan]]
slug = "cursor-pro"
tool = "cursor"
billing = "credits"
monthly_usd = 20
credit_to_usd = 0.04
allocation = "credits"
starts_on = "2026-01-01"
```

See [`docs/samples/ai-plans.toml`](samples/ai-plans.toml) for a complete example.

### Step 3 — Install hooks

```bash
halyard install-hook          # Claude Code
halyard install-cursor-hook   # Cursor
halyard install-gemini-hook   # Gemini CLI
```

From here, every AI session is captured automatically.

### Step 4 — Track human time

```bash
halyard start acme:auth
# ... do the work ...
halyard stop
```

### Step 5 — Run a report

```bash
halyard report
halyard report --ledger    # includes allocated subscription costs
```

### Step 6 — Confirm inferred attribution

```bash
halyard confirm-attribution
```

Sessions without an explicit project tag get attribution inferred from
overlapping timeclock entries. This command lets you confirm or reject each
inference.

### Step 7 — Set budget alerts

```bash
halyard set-budget acme --daily 15.00 --monthly 300.00
halyard budget
```

### Step 8 — Invoice with AI evidence

```bash
halyard invoice acme --period 2026-05 --include-ai-evidence
```

This generates `invoices/2026-05-001-acme.md` with an AI Usage Evidence
appendix showing session counts, token totals, and cost breakdown.

### Step 9 — Check your service record

```bash
halyard honors
```

Shows your rank (based on attributed sessions), watch streak, earned medals,
and Passport stamps — one per AI tool you've used.

### Step 10 — View your voyage roster

```bash
halyard voyage
```

Lists every project you've worked on with its current stage and session
progress. Set a custom budget target:

```bash
halyard voyage set acme --sessions 30
```

When a project moors (target hit or 14 days quiet), it earns a sea creature
badge assigned by personality — visible in `halyard voyage` and on The Bridge.

---

### What you now have

- `ai-sessions.log` — every AI session, plain text, append-only
- `time.timeclock` — human time in hledger-compatible format
- `invoices/2026-05-001-acme.md` — invoice with AI evidence appendix
- `voyages.toml` — project voyage stages and earned sea creatures
- Full cost breakdown: direct API + allocated seat/credit plans

For an explanation of `captured`, `allocated`, and `inferred`, see
[`docs/trust-model.md`](trust-model.md). For troubleshooting first capture,
see [`docs/troubleshooting.md`](troubleshooting.md).
