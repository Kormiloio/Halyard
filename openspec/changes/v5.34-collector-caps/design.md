# v5.34 — Design

## Why one reader instead of four fixes

v5.32 solved this correctly for Codex. Copying that solution into three more
collectors would have produced four near-identical implementations of the
same bounded-streaming logic, free to drift — which is how the original cap
came to exist in four places with four different constants (25, 25, 50, 50
MB) and no shared rationale.

`iter_bounded_lines` is the whole behaviour: symlink refusal, per-line cap,
total budget, truncation reporting. Collectors pass a `label` so the log
line names which one truncated. `codex_app._iter_jsonl_lines` survives as a
thin delegation because it carries Codex-specific constants and its
docstring records the v5.32 history.

## Why `gemini_otel` is fixed differently

Its guard looked identical but protected a different read:

```python
text = fh.read(_MAX_OTEL_BYTES)   # already bounded
```

Memory was never at risk there, so removing the bound would have been a real
regression. The defect was narrower: `_safe_path` *also* rejected the file
on size, so a large OTel log produced no timing data at all rather than the
first 25 MB. Partial beats nothing. Only the rejection is removed.

Treating all four sites as the same bug would have been the easy mistake.

## Why the regression guard is source inspection

`test_no_collector_rejects_a_file_on_total_size` greps for `st_size >`.
Normally that is a poor test — it asserts implementation, not behaviour.

Here it is the right tool, because the failure mode *is* the absence of
behaviour. An oversized file returned `None` and the caller skipped the
session: no exception, no log line, no partial result, nothing observable.
A behavioural test cannot distinguish "correctly found no sessions" from
"silently dropped the largest one" without knowing what should have been
found. That is exactly why four copies of this survived review.

The companion test asserts each collector *does* reference
`iter_bounded_lines`, so removing the cap by deleting the read entirely
would not pass either.

## What is not covered

The tests bound the reader with small synthetic files; the multi-hundred-MB
claims in the proposal come from measurements against the real files and are
recorded there, not reproduced in the suite. Writing an 800 MB fixture to
assert a 1 GiB budget would trade minutes of CI time for no additional
confidence.
