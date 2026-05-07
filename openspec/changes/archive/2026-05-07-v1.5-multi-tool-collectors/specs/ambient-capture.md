# Spec: Ambient Capture (Hub and Git Inference)

---

## Hub

**WHEN** `halyard init --hub` is run in a directory  
**THEN** the directory is initialised as a normal Halyard project  
**AND** `~/.halyard/hub` is written with the directory's absolute path

**WHEN** `halyard hub` is run and no hub is configured  
**THEN** a message is shown explaining that sessions outside project trees are dropped  
**AND** the user is told how to fix it

**WHEN** `halyard hub` is run and a hub is configured  
**THEN** the hub path and session count are shown

**WHEN** `halyard hub <path>` is run  
**AND** `<path>` contains a `halyard.toml`  
**THEN** `~/.halyard/hub` is updated to `<path>`

**WHEN** `halyard hub <path>` is run  
**AND** `<path>` does not contain a `halyard.toml`  
**THEN** an error is shown directing the user to run `halyard init` there first

**WHEN** `~/.halyard/hub` contains a path to a directory that no longer exists  
**THEN** `find_hub()` returns `None` (silently — missing hub = no hub)

**WHEN** a hook fires and `find_project_dir()` returns `None`  
**AND** `find_hub()` returns a valid path  
**THEN** the session is written to the hub's `ai-sessions.log`

**WHEN** a hook fires and both `find_project_dir()` and `find_hub()` return `None`  
**THEN** no record is written and the hook exits 0 silently

---

## Git inference

**WHEN** `infer_project(cwd)` is called  
**AND** `cwd` has an `origin` remote  
**AND** `~/.halyard/repos.toml` has an exact match for the normalized remote  
**THEN** the mapped project slug is returned

**WHEN** `infer_project(cwd)` is called  
**AND** `cwd` has an `origin` remote  
**AND** a wildcard pattern in `repos.toml` matches the normalized remote  
**THEN** the mapped project slug is returned  
**AND** exact matches take no priority over wildcard matches (first match in config order wins)

**WHEN** `infer_project(cwd)` is called  
**AND** `cwd` has an `origin` remote  
**AND** no mapping matches  
**THEN** `git/<repo-name>` is returned  
(where repo-name is the last path segment of the normalized remote)

**WHEN** `infer_project(cwd)` is called  
**AND** `cwd` is not a git repo (or has no `origin` remote)  
**THEN** `None` is returned

**WHEN** `git remote get-url origin` takes longer than 2 seconds  
**THEN** the subprocess is killed and `None` is returned  
(hook latency must not block the developer's workflow)

---

## `halyard link-repo`

**WHEN** `halyard link-repo acme:auth` is run inside a git repo with an origin  
**THEN** the normalized remote is added to `~/.halyard/repos.toml` under `[repos]`  
**AND** future sessions from that repo carry `project=acme:auth`

**WHEN** `halyard link-repo acme:auth` is run  
**AND** the remote already exists in `repos.toml` with a different slug  
**THEN** the existing entry is updated (not duplicated)

**WHEN** `halyard link-repo acme:auth` is run outside a git repo  
**AND** no `--remote` flag is given  
**THEN** an error is shown directing the user to pass `--remote` explicitly

**WHEN** `halyard link-repo acme:auth --remote github.com/acme/*` is run  
**THEN** the wildcard pattern is written to `repos.toml` verbatim  
**AND** all repos under `github.com/acme/` will infer `project=acme:auth`

---

## Remote URL normalization

The following inputs all normalize to `github.com/acme/auth-service`:

- `https://github.com/acme/auth-service.git`
- `https://github.com/acme/auth-service`
- `git@github.com:acme/auth-service.git`
- `ssh://git@github.com/acme/auth-service`

Normalization rules:
1. Strip protocol prefix (`https://`, `http://`, `git://`, `ssh://`)
2. Convert `user@host:path` → `host/path`
3. Strip `.git` suffix
4. Strip trailing `/`
