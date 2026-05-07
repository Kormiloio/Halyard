# Halyard — Live Demo Script

**Audience:** People with no technical background.
**Format:** You talk, the terminal is on screen. Read the narration out loud. Type
the commands. The output speaks for itself.
**Time:** ~10 minutes.

---

## Opening (talk, no typing)

> "Let me start with a question. How many of you have used ChatGPT, or asked an
> AI to help you with something — write an email, explain a topic, help with
> homework?"

*(Pause for hands.)*

> "Now — do you know how much that cost? Not in dollars necessarily, just…
> do you have any idea?"

*(Most people don't.)*

> "That's the problem we solved. When professionals — developers, consultants,
> designers — use AI tools to do work for clients, the AI costs money. But
> there's been no way to track it. It just disappears. Nobody knows where the
> money went. And when it's time to bill the client, there's nothing to show
> them.
>
> We built Halyard. It's like a receipt printer for AI work. Every time you
> use an AI tool, Halyard writes down what happened — which tool, which model,
> how long, how much it cost — automatically, in plain text, on your own
> computer. No cloud required. No subscription. Just a log file you own.
>
> Let me show you."

---

## Part 1 — Setting up a project (2 min)

> "Imagine you're a freelancer. You have a client called Acme Corp. They've
> asked you to build an authentication system for their app. You're going to
> use AI tools to help you move faster. Let's set Halyard up."

```bash
mkdir ~/demo-acme && cd ~/demo-acme
halyard init
```

> "That one command just created your project. It made a few plain text files.
> Let's look at what's inside."

```bash
ls
```

*Output shows: `halyard.toml`, `clients.toml`, `projects.toml`, `ai-plans.toml`*

> "Plain text files. No database. No cloud account. Everything lives right
> here on your computer. Let's tell Halyard about our client."

```bash
cat clients.toml
```

> "We fill this in with Acme's details and our hourly rate. And the project:"

```bash
cat projects.toml
```

> "Now let's tell Halyard how we pay for our AI tools. I use Claude — I pay
> $20 a month for it. I use Cursor — that's another $20. Halyard needs to
> know this so it can figure out how to split those costs across projects."

```bash
cat ai-plans.toml
```

---

## Part 2 — The magic: automatic capture (2 min)

> "Here's the part that surprised everyone when we showed them. Once you
> install a hook — that's a tiny trigger that fires every time you use an AI
> tool — Halyard captures the session automatically. You don't do anything.
> You just… work."

```bash
halyard install-hook
```

> "That just wired Halyard into Claude Code. Same thing exists for Cursor,
> for Gemini. Now every AI session gets recorded. Let me show you what that
> looks like."

```bash
cat ai-sessions.log
```

*Show a few log lines. Point to one:*

> "See this line? That's one AI session. It says: started at 10:14, ended at
> 10:42, used Claude, model was claude-sonnet, 4,300 input tokens, 800 output
> tokens, cost 14 cents. Automatically written. Every single session.
>
> It's like a bank statement — but for AI work. And just like a bank statement,
> it's plain text. You can read it, search it, email it, put it in a
> spreadsheet. We own it. It's not locked in someone else's cloud."

---

## Part 3 — Tracking human time (1 min)

> "Halyard also tracks your regular work time. When you start working on
> a task, you type this:"

```bash
halyard start acme:auth
```

> "When you're done:"

```bash
halyard stop
```

> "That's it. Your human hours and your AI usage are now both tracked,
> tied to the same project."

---

## Part 4 — The report (2 min)

> "Okay so you've been working for a few weeks. AI sessions are piling up.
> Let's see where things stand."

```bash
halyard report
```

*Pause to let people read the output.*

> "This tells you everything. Human hours: 3 hours 20 minutes this month.
> AI sessions: 14. AI cost: 73 cents direct from the API.
>
> But wait — 73 cents doesn't tell the whole story, because I also pay
> my $20-a-month Claude subscription. Halyard tracks that too. Let's see
> the full picture:"

```bash
halyard report --ledger
```

> "Now we see the real number. $44.93 in AI costs this month — that's the
> direct API cost plus the portion of my subscription that went to this
> project. And it's broken down by project. The client can actually see
> what their work cost in AI.
>
> Notice those labels — 'captured', 'allocated', 'mixed'. That's Halyard
> telling you how confident it is in each number. 'Captured' means we
> measured it directly from the API. 'Allocated' means it's an estimate
> from a subscription plan. Honest about the difference."

---

## Part 5 — The invoice (2 min)

> "Now it's the end of the month. Time to bill the client. Normally a
> freelancer would guess at how long things took and hope the client
> believes them. With Halyard:"

```bash
halyard invoice acme --period 2026-05 --include-ai-evidence
```

> "Let's look at what it generated."

```bash
cat invoices/2026-05-001-acme.md
```

*Scroll to the AI evidence appendix.*

> "At the bottom of the invoice there's an AI Usage Evidence section. It
> shows the client: 14 sessions, which tools, which models, exactly how
> many tokens, exactly what it cost. They don't have to take your word
> for it. The log file is right there. It's like showing receipts.
>
> Clients trust this. It turns 'trust me, AI helped' into 'here are the
> numbers.'"

---

## Part 6 — The live dashboard (2 min)

> "One more thing. If you want to watch your AI usage in real time — like
> a cockpit for your work — we built this:"

```bash
halyard tui
```

*Let it sit on screen for a moment.*

> "This updates live. Every time an AI session completes, it appears here.
> Sessions, costs, which models you're hitting — all updating as you work.
>
> It has keyboard shortcuts so you can navigate without touching the mouse:"

| Key | What it does |
|-----|--------------|
| `d` | Show only today's sessions |
| `w` | Show this week |
| `m` | Show this month |
| `a` | Show all time |
| `↑` `↓` | Move up and down the project list |
| `Enter` | Drill into a project — see its sessions in detail |
| `Esc` | Go back |
| `b` | Filter by git branch — see only work on a specific branch |
| `p` | Toggle between hub view and single-project view |
| `?` | Open this keyboard help inside the dashboard |
| `q` | Quit |

*Press `?` to show the help modal on screen.*

> "Press `?` and it shows you the whole cheat sheet right there in the app.
> You never have to remember them — just hit question mark."

*Press `m` to switch to month view, then arrow down and Enter to drill into a project.*

> "See — I can arrow down to a project and hit Enter to zoom in. It shows me
> every session for that project: when it happened, how long, which model,
> what it cost. Then Escape takes me back to the overview."

*Press `Esc`, then `q` to exit.*

---

## Part 7 — For teams (1 min, talk only or show if org.db is populated)

> "Everything we just saw is for one person. But what if you're a manager
> at a company with 50 developers, all using AI tools? Who's using what?
> How much is it costing? Which projects are AI-heavy?
>
> We built an org layer. Each developer runs `halyard sync`. Their sessions —
> just the metadata, never the actual content of what they asked the AI —
> go into a shared database. Then a manager can run:"

```bash
halyard org-report summary --period 2026-05
halyard org-report teams
halyard org-report finance --csv exports/2026-05.csv
```

> "And they get the full picture across the whole organization. Team by team.
> Project by project. It's the same data, just rolled up.
>
> That last command exports a CSV file for the finance team — with cost
> centers, trust labels, everything they need to actually do chargeback
> accounting."

---

## Closing (talk, no typing)

> "So what did we build?
>
> For a freelancer: automatic AI session capture, human time tracking,
> cost allocation across projects, and invoices with receipts attached.
>
> For a company: a rollup layer that tells managers and finance exactly
> what AI is costing, which teams are using it, and where the money is
> going — without ever seeing what anyone actually typed into the AI.
>
> Everything is plain text. You own all of it. There's no Halyard account.
> No cloud. No vendor lock-in. If we disappear tomorrow, your files still
> work — they're just text files with a simple format.
>
> That's Halyard."

---

## If they ask questions

**"How does it know what model I used?"**
> The hook captures the response from the AI tool — it includes the model
> name and token counts. Halyard reads that data and writes it to your log.

**"What if I use a subscription — like Claude for $20/month — does it know
the real cost?"**
> It can't know exactly because subscriptions don't charge per message. But
> it allocates the subscription cost proportionally across your sessions
> based on how much time you spent. It tells you it's an estimate —
> that's what the 'allocated' trust label means.

**"Does Halyard see my prompts? What I actually said to the AI?"**
> No. Never. It only captures metadata: timestamps, model, token counts,
> cost. The actual words you typed stay on your computer. Even in the org
> dashboard, managers only see metadata.

**"Why plain text? Why not a proper database?"**
> Because you can read plain text in 10 years without any software. You
> can grep it, email it, put it in Excel. Databases get abandoned.
> Text files last forever. The log format is documented — anyone can
> write a parser in an afternoon.
