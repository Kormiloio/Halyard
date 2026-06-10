# v5.19 — Tasks

Source: `docs/reviews/2026-06-pre-release-audit.md`. Implemented by the human
integrator (auth-critical, design-sensitive — done sequentially, not
parallelized). Owner-approved design: token everywhere + AF_UNIX peer-cred
ingest listener.

## B2 — token lifecycle [service.py] ✅

- [x] `_load_or_create_token`: create via
      `os.open(O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW, 0o600)` (no temp, no
      world-readable window, symlink-safe, race-free). `_force_replace_token`
      handles an untrusted occupant (EEXIST/ELOOP).
- [x] `~/.halyard` created `0o700` (`_ensure_halyard_dir`).
- [x] Adopt a pre-existing token only if `st_uid == getuid()` and regular
      file; tighten loose perms fail-closed (chmod not suppressed)
      (`_read_token_if_ours`, uses `lstat`).
- [x] Windows guards (`hasattr(os, "getuid")`, `_O_NOFOLLOW` fallback to 0).
- [x] Regression test (tests/test_v519_b02_token_lifecycle.py, 8 tests):
      0o600 file + 0o700 dir; garbage/planted-symlink rejected & victim
      untouched; loose perms re-tightened; no leftover temp; stable adopt.

## Peer-cred helper [src/halyard/peercred.py] ✅

- [x] `peer_uid(sock) -> int | None` via `SO_PEERCRED` (Linux) / `getpeereid`
      (macOS, ctypes with explicit signature); AF_UNIX-guarded; None elsewhere.
- [x] `peer_is_self(sock) -> bool` (fails closed without `os.getuid`).
- [x] Unit test (tests/test_v519_peercred.py, 4 tests): AF_UNIX pair → self;
      non-unix → None; Windows-sim fails closed.

## B4-auth — TCP endpoints [hub_server.py, hub_client.py, dashboard.py] ✅

- [x] Transport-aware `_authorized()`: AF_UNIX peer → `peer_is_self`; TCP →
      bearer token via `X-Halyard-Token` header, `halyard_token` cookie, **or
      `?token=` query param** (EventSource cannot set headers).
- [x] `_authorized()` guards on `/v1/ingest`, `/v1/state`, `/v1/collisions`,
      and `/v1/events` (`/health` stays open).
- [x] `/v1/traces` stays unauthenticated (loopback) for Copilot OTLP compat.
- [x] **Browser-CSRF hardening (owner finding #1):** `_csrf_ok()` requires
      `Content-Type: application/json` on every POST (a cross-origin CORS
      "simple request" can only be text/plain/form-encoded → blocked; JSON
      forces a preflight the hub never answers) and rejects
      `Sec-Fetch-Site: cross-site`. Applied in `do_POST` (covers ingest +
      the open `/v1/traces`). Machine clients already send application/json.
- [x] `_MAX_SSE_CONNECTIONS` cap (32) via `_sse_acquire`/`_sse_release`.
- [x] `hub_client.ingest_line`/`read_state`/`check_collisions` send
      `token=True`; `dashboard.py` renders the SSE URL with `?token=`.
- [x] Updated 5 existing hub test files (v4/v41/v42/v43/v5-collision) to send
      the token; 87 hub blast-radius tests green.
- [ ] Forged-timestamp plausibility bound on `/v1/traces` — deferred (minor;
      `/v1/traces` only writes telemetry, and the v5.18 cap/timeout already
      bound impact). Tracked as a follow-up.

### Regression test for the CSRF / auth surface ✅

- [x] `tests/test_v519_b04_auth.py` (8 tests): unauth ingest → 401; valid
      token → 200; text/plain → 415; `Sec-Fetch-Site: cross-site` → 415;
      `/v1/state` unauth → 401; SSE `?token=` → 200; SSE no-token → 401;
      `/health` stays open. Full suite incl. TUI green.

## B4-auth — AF_UNIX ingest listener (new) [hub_server.py, hub_client.py] ✅

- [x] `_ThreadingUnixHTTPServer` (ThreadingMixIn + UnixStreamServer) on a
      **port-keyed** socket `~/.halyard/hub-{port}.sock` (0o600, dir 0o700),
      reusing the same `_Handler` → identical routing/auth. Port-keying stops a
      test hub (:54318) from clobbering a real hub (:4318).
- [x] Authenticates by peer-cred via the transport-aware `_authorized()`
      (`peer_is_self`); `_host_ok()` skips the Host check for AF_UNIX (no
      browser/DNS). No token required on the socket.
- [x] `hub_client` prefers the socket (`_UnixHTTPConnection`, port-keyed
      `_unix_socket_path`; skipped on Windows / `HALYARD_HUB_HOST` override);
      falls back to TCP+token only on a *connection* failure.
- [x] Lifecycle: `_start_unix_listener` (best-effort; never blocks TCP) unlinks
      a stale socket then binds + chmods 0o600; `stop()` shuts it down and
      unlinks. POSIX-only (`_AF_UNIX_AVAILABLE`).
- [x] Regression test (tests/test_v519_afunix_listener.py, 3 tests): socket
      0o600 + removed on stop; ingest over the socket with **no token**
      succeeds (peer-cred) and writes the ledger; CSRF Content-Type still
      enforced. Broader hub suite (75 tests) unaffected.

## B3 — token disclosure [dashboard.py] ✅

- [x] `_send_dashboard` sets the `halyard_token` cookie ONLY when the request
      already presents the valid token (`_request_token_valid()`: launch-URL
      `?token=`, `X-Halyard-Token` header, or existing cookie; constant-time).
- [x] `run_dashboard` opens the browser at `…/?token=<tok>` so the legit user
      is authed on first load and receives the cookie for subsequent POSTs.
- [x] Regression test (tests/test_v519_b03_token_cookie.py, 4 tests):
      unauth GET → no `Set-Cookie` (no token leak); `?token=` / valid cookie →
      cookie set; wrong token → no cookie. 53 dashboard tests still green.
- Note (separate, lesser, follow-up): an unauthenticated GET still *renders*
      the page (data visible), only the token is withheld. Gating the page
      body on auth is a larger change tracked separately; the audited
      escalation (token → writes) is closed.

## B5 — timer path traversal [hub_server.py] ✅

- [x] `_target_project_dir` constrained to the `read_registry()` allowlist
      (resolved-path match); unregistered dirs return None → caller falls back
      to the hub's own project dir. The timeclock-parent fallback is
      constrained the same way.
- [x] `project` run through `_safe_field` on the timer path (mirrors presence).
- [x] Regression test (tests/test_v519_b05_timer_path.py, 3 tests): arbitrary
      `project_dir`/`timeclock` rejected; registered accepted. 83 existing
      hub/timer tests still green.

## B13 — HMAC downgrade [state_integrity.py] ✅

- [x] Sidecar-as-strength-floor enforced at the verification choke point
      (`read_trusted_state`): `_MODE_STRENGTH` map; if a stronger sidecar
      exists than the resolved mode, verify with the stronger scheme. The old
      `mode == "off"`-only guard in `read_global_trusted_state` is subsumed
      (simplified). Protects every caller, not just the global entry point.
- [x] Regression test (tests/test_v519_b13_hmac_downgrade.py, 2 tests): forged
      content + unkeyed `.sha256` + `mode="hash"`/`"off"` is rejected because
      the `.hmac` sidecar forces HMAC; genuine hash-only file still reads. 43
      existing integrity tests green.

## Gate ✅

- [x] `uv run pytest` (full suite **incl. TUI**) green.
- [x] `uv run ruff check .` + `ruff format --check .` clean.
- [x] `uv run mypy src/` clean.
- [x] Roadmap entry (project.md #90); audit report §0 → all 23 blockers fixed,
      AF_UNIX listener done, nothing outstanding.

## Parallel-review follow-ups (post-merge audit by owner) ✅

A second outside code review caught five findings the in-tree v5.19 work
missed (three P1, two P2). All closed here before public release. Final
gate: 1712 tests green, ruff/format/mypy clean.

### B3-page — dashboard page itself is auth-gated [dashboard.py] ✅

- [x] `do_GET` / `do_HEAD` now require a valid token (header / cookie /
      launch-URL `?token=`) **before** rendering. The original B3 fix only
      stopped the Set-Cookie leak; the HTML body still leaked the full
      ledger (costs, projects, branches, home-directory paths) to a
      co-located `curl`. Returns 401 + terse plain-text hint on failure.
- [x] Regression coverage rewritten in tests/test_v519_b03_token_cookie.py:
      unauth GET → 401 + no markup; unauth HEAD → 401 + no body; valid
      token (URL / cookie / header) → 200 + page; wrong token → 401.
- [x] `test_dashboard.py` host-validation helper now sends the token so
      it still probes Host semantics in isolation.

### B5-followup — rejected timer target is a hard 400 [hub_server.py] ✅

- [x] `_target_project_dir` raises `_RejectedTargetDirError` when the
      client supplies a `project_dir`/`timeclock` not in the registry.
      The original B5 fix returned `None` for both "no target supplied"
      and "rejected", so the timer handler silently fell back to the
      hub's own project — a token-holding client could redirect a timer
      write by passing any path.
- [x] Timer handler catches the typed rejection and responds 400. Bare
      `None` (no target supplied) still falls back to the hub default.
- [x] Coverage updated in tests/test_v519_b05_timer_path.py and added in
      tests/test_v519_parallel_review_followups.py.

### B-DoS-mem — OTel accumulator memory bounds [vscode_otel.py] ✅

- [x] `_ingest_span` enforces three per-row caps so the unauthenticated
      `/v1/traces` path cannot grow one accumulator without bound:
      `_MAX_SESSION_ID_LEN=256`, `_MAX_MODEL_NAME_LEN=128`,
      `_MAX_MODELS_PER_SESSION=32`. The session-count cap in
      hub_server.py bounds *how many* accumulators live; these bound how
      big one can get.
- [x] Existing-model bumps still count after the cardinality ceiling so
      legitimate spans are not silently dropped.

### B-DoS-clen — reject negative Content-Length [hub_server.py] ✅

- [x] `_read_body` rejects `Content-Length < 0` with 400. Previously
      `int("-1")` passed the parse, and `rfile.read(-1)` would block
      until EOF/peer-close — a one-line local DoS against the only
      unauthenticated endpoint (`/v1/traces`).
- [x] Regression test in tests/test_v519_parallel_review_followups.py
      drives a live hub on the loopback to exercise the real dispatch.

### B-Reset — explicit integrity-mode migration [state_integrity.py] ✅

- [x] `migrate_integrity_mode(path, content, *, new_mode)` is the
      documented trusted reset path. The B13 sidecar-strength floor (an
      orphaned `.hmac` cannot be silently downgraded) had made the
      documented "switch integrity off / downgrade" workflow impossible:
      a plain `write_trusted_state(off)` left the stale `.hmac` in
      place, so the next read failed closed with IntegrityError.
- [x] The migration helper writes new content + sidecar via
      `write_trusted_state`, then removes any *strictly stronger* stale
      sidecar so the floor no longer pins reads. Routine writes keep
      their fail-closed behavior — only this explicit operation strips
      integrity, and only when the caller has authority (CLI flag,
      owner of `halyard.toml`).
- [x] Coverage: downgrade hmac→off, downgrade hmac→hash, regression
      guard that a plain `write_trusted_state(off)` after `hmac` still
      fails closed (the floor itself is intact).

### B-Format — CI formatting gate green ✅

- [x] `hub_server.py` reformatted; trailing whitespace removed from
      `openspec/changes/v5.0-duplicate-effort/design.md:7`.
- [x] `uv run ruff format --check .` clean; `git diff --check` clean.

## Parallel-review round 2 (full-codebase audit by owner) ✅

A second outside audit went past the v5.19 diff and read the whole codebase
(103 production modules, the VS Code extension, tests, contracts). Eight
findings, all closed here before public release. Final gate: 1722 tests
green, ruff/format/mypy clean.

### B-quickstart — default dashboard URL is usable [dashboard.py] ✅

- [x] `run_dashboard` now prints `http://localhost:<port>/?token=<tok>` —
      the URL the gated `GET /` will actually accept. The previous build
      printed a bare URL that returned 401 from the documented quickstart
      (`halyard dashboard` with the default `--open=False`).
- [x] `--open` continues to hand the same authenticated URL to the
      browser; the launch URL and the printed URL are now identical.
- [x] EADDRINUSE error rewritten to recommend the real command
      (`halyard dashboard`) rather than the product name ("Halyard
      Bridge"), which the reviewer mistook for a phantom subcommand.

### B-evidence — all-time evidence sums per-month subscription cost ✅

- [x] New `ledger.build_aggregated_ledger(sessions, plans, tc_entries, *,
      period_label)` runs `build_ledger` once per (year, month) covered by
      the session set and folds the entries — preserving each month's
      plan attribution so a $100/month seat plan with sessions in two
      months reports $200, not $100.
- [x] `evidence.build_evidence_data(..., all_time=True)` now routes
      through the aggregated builder.
- [x] `invoicing.render_ai_evidence_appendix` gained an
      `aggregate_months=` flag and `evidence.build_evidence_artifact`
      passes it on `all_time=True` so the markdown appendix matches the
      structured JSON.

### B-integrity-migrate — production CLI entry point [cli_config.py] ✅

- [x] New subcommand `halyard config integrity-migrate <mode>` (with a
      `-y/--yes` flag for non-interactive runs) is the documented reset
      path that calls `state_integrity.migrate_integrity_mode` on
      `~/.halyard/active` and `~/.halyard/hub`. Without this, the v5.19
      migration helper had no production caller and the documented HMAC
      recovery workflow still failed (the floor blocked any read).
- [x] An integrity failure on any tracked file aborts cleanly (exit 1)
      with a clear "inspect before retrying" hint — we never strip
      tamper-evidence from a file that already fails verification.

### B-cursor-order — Cursor hook parses payload before clearing state ✅

- [x] `handle_stop_hook` parses every untrusted `usage.*` field via the
      new `_coerce_int` helper BEFORE calling `_clear_session_start()`.
      Previously a malformed token field (e.g. `{"input_tokens": "abc"}`)
      raised inside a bare `int(...)` after the session state had
      already been cleared — and the outer `_run_hook` wrapper swallowed
      the exception to exit 0, silently discarding the turn.
- [x] `_coerce_int` falls through bad values to `0` rather than raising,
      consistent with the existing "tokens unavailable, not zero" trust
      label policy.

### B-health-branch — repeated-attempt detector uses first-class branch ✅

- [x] `work_health._day_key` now reads `AiSession.branch` first and only
      falls back to the legacy `branch:` tag. Three sessions on three
      distinct modern branches no longer collapse to one key — the
      repeated-attempts signal now reflects reality, not the absence of
      a retired tag.

### B-status-client — by_client rolls projects up to client prefix ✅

- [x] `status_snapshot._spend` aggregates `rep.by_project` buckets by
      their `client:project` prefix before sorting / truncating into
      `by_client`. `acme:web` and `acme:api` now report under one
      `acme` client bucket; the top-N truncation is not dominated by
      one heavy client's internal projects.

### B-rate-only — rate-history parser reads context-line slug ✅

- [x] `config_history.rate_history_from_git` now picks the governing
      `slug` from both `+`-added AND ` `-context diff lines, so a commit
      that changes only `hourly_rate = 100 → 150` (no slug line in the
      hunk) is no longer silently dropped from the audit trail.
- [x] `-`-deletion lines are explicitly ignored so the OLD slug never
      pollutes the in-effect mapping for the lines that follow.

### B-port-flake — hub fixture uses an ephemeral port ✅

- [x] `tests/test_v4_hub_server.py` `hub` fixture now binds `port=0` and
      yields the kernel-chosen port via `server.port`. The hard-coded
      `54318` made the suite fail whenever any other process held that
      port (concurrent test invocation, leftover hub, unrelated
      service).

## Parallel-review round 3 (full live-worktree audit by owner) ✅

A third outside audit went past the v5.19 diff again, this time including
older unchanged code (log_agent, config_history's full structural model)
and previously-undiagnosed cross-month edge cases. Eight findings, all
closed here before public release. Final gate: 1733 tests green,
ruff/format/mypy clean.

### B-end-month — aggregated ledger buckets by `session.end` [ledger.py] ✅

- [x] `build_aggregated_ledger` now groups by `sess.end.{year,month}`.
      Billing-period selection (`invoicing.py:139–244`) is end-based,
      so a Jan 31 23:50 → Feb 1 00:10 session is February work; the
      previous start-based bucketing gave it January's plan instead.

### B-evidence-month — evidence pins ledger to the requested month ✅

- [x] `evidence.build_evidence_artifact` and `evidence.build_evidence_data`
      now pass / pin to the *requested* period (`period.year`/`period.month`)
      rather than re-deriving `min(s.start)`. A session whose start lay in
      the prior month (and was only selected by an end-based reader, such
      as the invoice path) previously ran the ledger for that prior month
      → the requested month's active plan was inactive → $0.
- [x] Markdown path threads `ledger_year=`/`ledger_month=` through
      `render_ai_evidence_appendix`, matching the invoice-attached
      evidence path that already pinned (v5.17/B16).

### B-publish-perm — `publish.yml` keeps `contents: read` permission ✅

- [x] Adds `contents: read` alongside `id-token: write` so
      `actions/checkout` can read the repo. Defining job-level
      permissions makes every omitted permission *unavailable*, so the
      checkout step would otherwise fail.

### B-cursor-defer-clear — clear state only after persistence succeeds ✅

- [x] `_clear_session_start()` is invoked in three explicit positions:
      after a successful `append_session(...)`, after a successful
      `write_unattributed_session(...)`, and after the deliberate
      no-evidence/implausible/synthetic rejection. Any crash before
      persistence (workspace parsing, git inspection, AiSession
      construction) leaves the session-start file intact so the next
      stop fire (or `halyard repair`) can claim the recoverable turn.
- [x] Workspace-roots parsing is also defensive: a non-string root no
      longer flows into `Path(...)`.

### B-trust-merge — aggregated trust labels reduce honestly [ledger.py] ✅

- [x] `build_aggregated_ledger` now collects the SET of per-month trust
      labels per project and reduces via `_merge_trust_labels(...)`:
      captured + allocated across months → "mixed", `mixed` is
      preserved, `unallocated` falls back only when no allocated cost
      shows up. First-month-wins masked the fact that part of an
      all-time row's cost was estimated.

### B-rate-structural — rate history parses each historical TOML snapshot ✅

- [x] `config_history.rate_history_from_git` now walks `git log --reverse`
      of `clients.toml`, fetches each commit's full file via
      `git show <sha>:clients.toml`, and parses it as TOML. A
      `RateChange` is emitted whenever a slug's `hourly_rate` (or legacy
      `rate`) differs from the previous commit's value.
- [x] Diff geometry (±3 context lines) no longer matters — a real
      `[[client]]` entry that carries `name`, `email`, `address`, etc.
      between `slug` and `hourly_rate` correctly records its rate
      changes.
- [x] Malformed historical snapshots are skipped without aborting the
      audit. `_safe_float` is retained for the public security-test
      contract even though the new path doesn't use it.

### B-log-agent-branch — log_agent reads first-class `AiSession.branch` ✅

- [x] `_filter_sessions(... filters.branch)` matches `session.branch == X`
      first and falls back to the legacy `branch:<X>` tag for older
      ledger lines. Same fix as v5.19/B-health-branch, but applied to
      the older `log_agent` query surface — confirms the reviewer's
      sweep covered unchanged production paths.

### B-doc-polish — dashboard 401 hint + trust-model recovery docs ✅

- [x] The dashboard 401 body now points users at the real
      `halyard dashboard --open` command (and the printed `?token=` URL),
      not the phantom `halyard bridge`.
- [x] `docs/trust-model.md` recovery section documents
      `halyard config integrity-migrate <off|hash|hmac>` instead of the
      old "set off, restart timer, re-enable" trick (which never worked
      because the B13 floor blocked the read in the first place).

## Parallel-review round 4 — single finding ✅

### B-rate-rename — rate history preserved across file renames ✅

- [x] `rate_history_from_git` now walks ``git log --follow --name-only``
      newest-first so each commit reports its own path, fetches that
      historical path via ``git show <sha>:<path>``, and reverses the
      collected snapshots in Python. The round-3 structural fix used
      ``--reverse`` and a hard-coded `clients.toml` filename, so
      ``git show <sha>:clients.toml`` failed for every pre-rename
      commit — e.g. a ``customers.toml → clients.toml`` rename
      truncated history from ``[100, 125, 150]`` down to ``[150]``.
- [x] New helper ``_historical_clients_toml_snapshots`` returns
      ``(sha, effective_date, contents)`` tuples newest-first;
      ``_git_show_path`` replaces the old hard-coded
      ``_git_show_clients_toml``.
- [x] Regression test (tests/test_v519_parallel_review_round4.py, 2
      tests): the rename scenario returns ``[100, 125, 150]``; the
      no-rename happy path still returns ``[100, 150]``. 24 existing
      rate-history tests still green. Final gate: 1735 tests pass,
      ruff/format/mypy clean.
