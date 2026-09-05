# v5.31 — Tasks

## Code

- [x] `orchestration._adopt_timer_committed_by_hub(slug)`: reconcile via
      `hub_client.read_state()` on a fresh connection. Adopt only when the
      hub is reachable *and* names our slug *and* the on-disk record
      agrees.
- [x] Call it from `start_timer` between the hub attempt and the local
      fallback, `direct=False` only.
- [x] Return the on-disk `ActiveTimer` so `started` / `elapsed_minutes`
      are the timer's real values, not a reset clock.
- [x] `_start_timer_local` and the `direct=True` path unchanged.

## Tests (`tests/test_v531_hub_start_lost_response.py`)

- [x] Lost response + hub confirms our slug → adopts, no raise. **Fails
      without the fix** with the real production error.
- [x] Lost response + hub unreachable → still raises `TimerAlreadyRunning`
      (protects a stale active file from silent adoption).
- [x] Hub names a different project → does not adopt.
- [x] Hub reports no timer → does not adopt.
- [x] Adopted timer reports the on-disk `started` / `timeclock`, not a
      reset clock. **Fails without the fix.**
- [x] Adoption writes no second clock-in entry. **Fails without the fix.**
- [x] `direct=True` never consults the hub.

## Verification

- [x] Confirmed the three behavioural tests fail on unfixed code with
      `TimerAlreadyRunning: Timer already running for 'acme:auth'` — the
      exact error the user would see — while the four guard tests still
      pass, since they assert unchanged behaviour.

## Gates

- [x] `uv run pytest` — 1839 passing (+7).
- [x] `uv run ruff check .` and `uv run ruff format --check .`
- [x] `uv run mypy src/`

## Docs

- [x] `openspec/project.md` — roadmap entry + test count.

## Out of scope (recorded, not done)

- [ ] `stop_timer` has the mirror-image race: the hub clears state, the
      response is lost, `_try_stop_timer_via_hub` returns `None`, and the
      local fallback reports `was_running=False` — telling the user
      nothing was running when their command did stop the timer. Less
      harmful (the desired end state was reached, only the report is
      wrong) but the same shape.
- [ ] Teaching `hub_client._request` to distinguish "sent but no
      response" from "never connected". The general fix, but it touches
      every hub call site and each needs its own reconciliation policy.
