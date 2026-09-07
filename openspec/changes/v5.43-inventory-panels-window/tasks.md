# v5.43 — Tasks

## The window

- [x] `render` builds a second, `all_time=True` report (`inventory`)
      alongside the month-scoped `report`.
- [x] Voyage Roster, Models (Mix) and Tools (Capture) read `inventory`.
- [x] Spend, outcome and period panels keep `report` — a month is what an
      invoice covers.

## The share metric

- [x] `CostBucket.work_tokens` — input + output only.
- [x] `_model_table` share is `work_tokens / total_work_tokens`.
- [x] Tokens column added, matching the Tools table's column set.

## The cost cell, which now has four honest states

Found while verifying against real data: the new Tokens column put 17.4M
tokens next to `$0.00` for Codex, which is exactly the misreading this
panel keeps producing.

- [x] `$X` — real API spend.
- [x] `n/a` (v5.41) — no published rate, so spend is unknown.
- [x] `credits` — `CostBucket.api_billed`. `sum_spend` counts only
      `billing == "api"`, so a Codex bucket sums to `0.00`; that is true as
      API spend and reads as free.
- [x] `$0.00` — `CostBucket.local`. A local zero is a *measurement*
      (v5.41). Distinct from `api_billed` on purpose: conflating them
      labelled an MLX model "billed to a subscription".

## Tests (`tests/test_v543_inventory_panels.py`, 10)

- [x] The month report drops last month's work — the behaviour that hid
      the project, asserted so it cannot surprise anyone again.
- [x] The inventory report keeps it.
- [x] A month boundary empties the month report but not the inventory.
- [x] Share splits by work, not cost (equal cost, 9:1 tokens → 90/10).
- [x] An unpriced model still gets a share; cost share dropped it.
- [x] A zero-token model is `0%`, not `n/a` — zero work is a fact.
- [x] Each of the four cost states renders, and `credits` never prints
      `$0.00` while `local` never prints `credits`.

## Verified against real data

- [x] `kormilo:mycelium` now appears on the Voyage Roster (1 session,
      $28.45) — the question asked three times.
- [x] Models table ranks by work: gpt-5.6-terra 69%, muse-glimmer 11%,
      gpt-5.6-sol 8%, claude-opus-5 6%. It previously read four zeros.
- [x] Cost column reads `$732.78` / `credits` / `$0.00` / `n/a` across the
      four real cases on this machine.

## Also done

- [x] Restarted the user's dashboard process, up since Tue Sep 1 22:53 and
      therefore serving pre-v5.39 code — none of v5.39–v5.42 was visible to
      them. Both ports (7432 dashboard, 4318 OTEL receiver) confirmed back.

## Gates

- [x] `uv run pytest` — **2000 passing**.
- [x] `uv run ruff check .` / `uv run ruff format --check .`
- [x] `uv run mypy src/` — clean, 105 files.

## Docs

- [ ] Roadmap entry in `openspec/project.md`.
- [ ] `CHANGELOG.md` under Unreleased.
