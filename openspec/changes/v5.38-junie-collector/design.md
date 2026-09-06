# v5.38 — Design

## Why `billing="local"` rather than `cost=0.0`

Junie can run on-device, and it reports `cost: 0.0` truthfully when it
does. Three options:

1. Record `cost=0.0`, `billing="api"`. Wrong: it puts real on-device
   compute into the billable series at zero, so a month of heavy local work
   looks identical to a month of no work at all in every spend view.
2. Drop local rows. Worse: the tokens are real usage, and usage reporting
   is half of what Halyard is for.
3. Record the tokens, mark the billing mode. `sum_spend` already filters on
   `billing == "api"` (v5.17), so this needs no new machinery.

The classification deliberately keys on the model name, not on
`cost == 0.0`. A hosted model can report zero for reasons that are not
"this was free" — a free tier, a promotional period, a provider billing
outage — and silently reclassifying those as local would quietly remove
real API usage from spend. A wrong `local` is invisible; a wrong `api` at
$0.00 is merely uninformative. The marker list is conservative for that
reason.

## Why the plausibility cap is skipped

`session_is_implausible` rejects spans over 12 h. The first implementation
used it and lost two of four real sessions, including the one the user had
asked about by name.

The cap's stated purpose (v5.21) is that "a whole-transcript row spanning
days is mostly idle wall-clock and corrupts duration reporting". That
reasoning is about *duration*, and the codebase now handles duration at the
right layer: v5.33 excludes over-cap sessions from timeclock
reconciliation, and v5.35 from the coverage denominator. Both were written
after this cap, and both chose to bound what a long session may *claim*
rather than discard it.

Applying the cap at import discards the tokens too, which nothing
downstream can recover. Codex already keeps its 653 h session for exactly
this reason.

## End time comes from the events, not the index

`updatedAt` in `index.jsonl` is rewritten when the session record is
touched; the events are written as work happens. Where the last event
timestamp is later, it is used. The event stream is the tighter bound on
real activity, and using it means a session still in progress reports an
end that reflects its last actual turn.

## Testing

The fixtures write real `index.jsonl` and `events.jsonl` structures rather
than mocking the reader, because the schema — `event.agentEvent.modelUsage`
— is the part most likely to drift upstream, and a mock would keep passing
after it did.

The two judgement calls above are pinned by tests that fail if reversed: a
hosted model reporting `0.0` must stay `api`, and a multi-day session must
survive import. Both are cases where the wrong behaviour is silent.
