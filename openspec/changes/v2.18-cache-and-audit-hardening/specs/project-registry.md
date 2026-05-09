# Spec: Project Registry

## File

`~/.halyard/projects`

## Format

One absolute path per line. UTF-8. Empty lines and lines starting with
`#` are ignored. No other syntax.

```
# Halyard project registry
/Users/mario/work/halyard
/Users/mario/clients/acme
/Users/mario/clients/beta
```

## Lifecycle

- Created on first `halyard init`. Mode `0644`.
- Appended to (deduplicated) on every subsequent `halyard init` in a new
  directory.
- Read by `halyard db sync`, `halyard report --all-projects`, and any
  other multi-project surface.
- Trimmed by `halyard projects forget <path>`.

## Discovery order for `halyard db sync`

1. Read `~/.halyard/projects`. For each path that exists and contains
   `halyard.toml`, treat it as a source.
2. Append `find_hub()` if a hub exists and isn't already covered.
3. Append `find_project_dir()` (CWD walk-up) if it's a project dir not
   already covered.
4. Sync sources in deterministic sorted order.

A registry path that no longer exists or no longer contains
`halyard.toml` is skipped with a `[yellow]Warning:[/]` to the user. The
path is not auto-removed; the user runs `halyard projects forget` if
they want it gone.

## CLI

```
halyard projects list                  # print registry contents
halyard projects forget <path>         # remove a path
halyard projects add <path>            # add a path explicitly
```

`halyard init` is the normal way to register; `add` is the escape
hatch for projects copied from elsewhere.

## Privacy

The registry is local-only. It is never read by `sync.py` egress (which
operates per-project anyway). It contains absolute paths but no project
contents or names beyond directory naming.

For the future enterprise sync (v3.3), the registry is *not* exported.
Each project decides individually whether to participate in egress, and
that decision is recorded in `halyard.toml` per project.
