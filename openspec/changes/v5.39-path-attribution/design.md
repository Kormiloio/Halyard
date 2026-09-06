# v5.39 — Design

## Why the path is stored rather than resolved at import

Resolving at import and storing only the result is simpler, and wrong. It
is exactly what the code did before: `infer_project(cwd)` ran, returned
None, and the directory was dropped. The information that would have made
the session recoverable was destroyed at the moment it was least useful.

Storing `source_path` means a user can declare a mapping *later* — after a
directory moves, after they notice a project missing from the dashboard —
and history resolves. That is the same reasoning as v5.36's slug alias and
v5.33's timeclock reconciliation: keep the evidence, resolve at read time,
never rewrite the append-only ledger.

## Why resolution runs before the collapse

`resolve_paths` is applied inside `parse_sessions`, ahead of
`collapse_gemini_sessions`. Order matters: the collapse picks one canonical
row per job group and (v5.36) inherits a project when the winner lacks one,
but only when the group agrees. Resolving paths first means every row in
the group gets the same project from the same mapping, so there is nothing
for the inheritance rule to arbitrate.

Resolving after would work for the single surviving row, but would leave
the inheritance step reasoning about a group where some rows had a project
and others did not — more states, no benefit.

## Why exact match

A prefix rule is the obvious convenience: map `~/Development` once, cover
everything beneath it. The observed data kills it. The Junie workspace root
`~/Development/kormilo` contains at least `halyard`, `mycelium`, `nautilus`
and more, and Junie records the root rather than the repository. A prefix
match would attribute every one of those projects' work to whichever slug
was declared first — moving billable tokens onto a project the evidence
does not support, which is precisely the failure v5.36 exists to prevent.

Exact matching means an ambiguous path stays unattributed until the user
resolves the ambiguity themselves. That is the honest outcome.

## Most-frequent cwd

A long-lived rollout records `cwd` on every `session_meta` and
`turn_context`, and those can disagree — a directory synced elsewhere
mid-session produced 347 records for one path and 83 for another. Taking
the last one is arbitrary: it reflects wherever the tool happened to be at
the final write.

Frequency reflects where the session spent its time and is robust to a
transient change. Ties break toward the first-seen path via `dict`
insertion order, which is where the session began.

The tally helper is tested directly rather than through a synthetic
rollout: the selection rule is what changed, and a fixture would have to
satisfy every unrelated precondition of the parser to reach it.

## Test isolation

`git_context._PATHS_CONFIG` is a module-level `Path.home()` constant, and
`resolve_paths` now sits on the universal read path — so without isolation
every test that parses a ledger consults the developer's real path map. An
order-dependent failure appeared before `_isolate_path_map` was added,
which is the same class v5.37's guard was built to make loud. Adding the
constant to conftest is the established pattern, alongside the registry,
logs, auto-timer, hub pointer and cache database.
