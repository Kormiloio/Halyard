# v2.37 — Smart Attribution: Design

## Attribution priority (updated)

| Priority | Source | Mechanism |
|---|---|---|
| 1 | Active timer | `~/.halyard/active` → `slug=` line |
| 2 | `halyard.toml` walk-up | Walk CWD → root, first `[project].slug` wins |
| 3 | `repos.toml` explicit mapping | git remote URL pattern → slug |
| 4 | Auto git slug | `git/<repo-name>` from remote |
| 5 | Unattributed | Written to `~/.halyard/unattributed.log` |

Priority 2 is the new addition. It sits above `repos.toml` because an explicit
declaration in the directory ("this folder belongs to this project") is more
specific than a global git remote pattern.

## `halyard.toml` walk-up (`_slug_from_halyard_toml`)

`git_context.infer_project(cwd)` calls `_slug_from_halyard_toml(cwd)` first.
The function walks from `cwd` up to the filesystem root. At each directory:

- If `halyard.toml` exists and has `[project].slug` → return the slug.
- If `halyard.toml` exists but has no `[project].slug` → **stop walking**
  (a halyard.toml without a slug is still a project boundary).
- If no `halyard.toml` → continue up.

This means a repo root `halyard.toml` with a slug covers every sub-directory
in that repo, and a sub-project `halyard.toml` (e.g., `fleet/app-01/halyard.toml`)
overrides the parent.

## `halyard adopt <path>`

Promotes an auto-tracked directory to a named project without the full
`halyard init` scaffold.

Steps:
1. Verify `halyard.toml` does not already exist (error if so — use `init`).
2. Detect current auto-slug from git remote (`git/<repo-name>`).
3. Suggest slug from repo name; prompt for confirmation unless `--slug`/`--yes`.
4. Write minimal `halyard.toml`:
   ```toml
   [project]
   slug = "<chosen-slug>"
   ```
5. Add `repos.toml` entry for the git remote (belt-and-suspenders for machines
   without a local `halyard.toml`).
6. Register path in `~/.halyard/projects`.
7. Report what changed and note that historical hub sessions remain under the
   old auto-slug (`halyard reattribute <old> <new>` to migrate — future).

## `AiSession.remote` field

All three collectors (Claude Code, Cursor, Gemini CLI) now call
`current_remote(cwd)` at session close and write the normalized result
(`host/owner/repo`, no protocol, no `.git` suffix) to the `remote=` key in
the log line.

Privacy constraints:
- Only the git remote URL is stored — never the local filesystem path.
- Non-git sessions write no `remote=` key; they remain fully anonymous.
- The field is optional and backward-compatible: old log lines without it
  parse cleanly with `remote=None`.

## Unattributed surfacing

`doctor.py` adds `_group_unattributed_by_remote(log_path)` which parses
`~/.halyard/unattributed.log` and returns `{remote: count}`. The existing
`state.unattributed` check now renders a grouped breakdown:

```
WARNING Unattributed       23 session(s) across 2 source(s)
        fix: run 'halyard adopt' in each repo:
          github.com/mario/fleet (14 sessions)
          github.com/mario/kormiloio.github.io (6 sessions)
          (no git remote) (3 sessions)
```

The dashboard Overview tab (`usage_pane.py`) renders the same grouping inline
with a `⚠` marker so it cannot be missed.
