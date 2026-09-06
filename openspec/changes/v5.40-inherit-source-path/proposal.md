# v5.40 — The collapse inherited the project but dropped the path

## Why

v5.39 shipped `source_path` so a session that could not be attributed at
import would still record *where it ran*, and `halyard link-path` could
reach it later. After merging it I re-imported Codex and checked the one
session that motivated the whole change. It still had no path:

```
job group codex:01a0435e   29 rows
  rows carrying source_path:              1
  canonical row  in+out = 2,019,287       source_path: none
  best row with a path  in+out = 107,376  loses the ranking
```

This is **v5.36's defect recurring for a different field.**

A Codex session that is re-imported as it grows produces several ledger
rows for one job. `collapse_gemini_sessions` picks one canonical row by
token count. v5.36 established that the winner should *inherit* a project
from the group when it has none — the rank answers "which row is most
complete in tokens", which says nothing about which row happened to carry
a field. That reasoning is not specific to `project`. But the
implementation was: `source_path` was not inherited, so the row that had
recorded the directory lost on tokens and the path went with it.

The consequence is that v5.39's remedy could not reach the session it was
written for. `link-path` matches on a recorded path; the collapse deleted
the recorded path; the session stayed unattributable.

## What

- `_canonical_gemini_row` inherits **both** `project` and `source_path`
  from the group when the winner lacks them.
- `_inherited_project` generalised to `_agreed(rows, attr)`. The old name
  is kept as a thin alias — the rule it encodes (agree, or leave it
  unresolved) is the part worth preserving, not the field it applied to.
- Unchanged: a group that *disagrees* still resolves to nothing. Guessing
  moves billable tokens onto evidence that does not support them.

## Result on real data

Six sessions now carry a path where five did, including the Mycelium
session that started this:

```
codex  08-27  project=(none)
  .../My Drive/Documents/ChatGPT/Mycelium
```

`halyard link-path` can now reach it.
