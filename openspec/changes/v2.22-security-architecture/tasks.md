# Tasks: v2.22 — Security Architecture

Forward spec for Sage's architectural security review findings (D-3, D-4, D-5)
and 10 identified test coverage gaps. None of these tasks are yet implemented.

## Spec & design
- [x] Write proposal.md
- [x] Write specs/security-architecture.md
- [x] Write design.md

---

## D-4: Plist XML injection

- [ ] Import `xml.sax.saxutils.escape` in `service.py`
- [ ] Wrap `project_dir` interpolation with `escape(str(project_dir))`
- [ ] Audit plist template for any other interpolated values; wrap each
- [ ] `tests/test_plist_xml_injection.py`
  - [ ] `test_plist_xml_safe_project_dir` — normal path produces valid XML
  - [ ] `test_plist_xml_injection_lt_gt` — project_dir with < > produces valid XML
  - [ ] `test_plist_xml_injection_ampersand` — project_dir with & produces valid XML
  - [ ] `test_plist_xml_injection_combined` — all three characters, parsed by xml.etree

## D-3: org.toml change detection

- [ ] Add `_org_hash_path(hub_dir: Path, org_id: str | None = None)` helper
  returning a hub/org-scoped path under `~/.halyard/org-hashes/`
- [ ] Implement `_check_org_hash(content: bytes) -> None`
  - Compute SHA-256 of content
  - Read existing hash from the hub/org-specific hash path if present
  - If hash differs: print warning to stderr; write new hash
  - If hash matches: no-op
  - If no stored hash (first run): write hash silently
- [ ] Call `_check_org_hash()` in the org.toml load path
- [ ] Review note: do not use a single global `~/.halyard/org-hash.txt`;
  switching between hubs/orgs must not warn or overwrite another baseline
- [ ] `tests/test_org_hash.py`
  - [ ] `test_first_run_no_warning` — no hash file → no warning, hash written
  - [ ] `test_unchanged_org_no_warning` — same content → no warning
  - [ ] `test_changed_org_warning_emitted` — changed content → warning printed
  - [ ] `test_changed_org_hash_updated` — new hash stored after change
  - [ ] `test_two_hubs_have_independent_org_hashes` — loading hub A then hub B
    does not warn or overwrite hub A's baseline

## D-5: Pricing table hash pinning

- [ ] Add `_pricing_hash_path()` helper returning `~/.halyard/pricing-hash.txt`
- [ ] Wrap pricing table HTTP fetch to verify Content-Length / completeness
- [ ] Implement `_check_pricing_hash(body: bytes) -> bool`
  - Compute SHA-256 of body
  - Read existing hash from `_pricing_hash_path()` if present
  - Return True (hashes match) or False (differ / no stored hash)
- [ ] On first fetch with no stored hash: accept validated table and persist
  table + hash
- [ ] On hash mismatch with existing stored hash: print warning and abort
  persistence unless caller explicitly accepts the changed table
- [ ] Add CLI acceptance path for changed table, e.g.
  `halyard update-pricing --accept-changed-table`; non-interactive runs fail
  closed unless the flag is present
- [ ] On truncated response: abort; do not update local table or hash
- [ ] `tests/test_pricing_hash.py`
  - [ ] `test_first_fetch_no_warning` — no stored hash → accept silently
  - [ ] `test_matching_hash_no_warning` — same body → no warning
  - [ ] `test_changed_pricing_table_warning` — changed body → warning printed
  - [ ] `test_changed_pricing_table_does_not_overwrite_without_accept`
  - [ ] `test_changed_pricing_table_accept_flag_overwrites_and_updates_hash`
  - [ ] `test_truncated_response_no_overwrite` — incomplete response → local table unchanged
  - [ ] `test_truncated_response_hash_not_updated` — incomplete response → hash file unchanged

---

## Test coverage gaps

### Gap 1: Session round-trip fidelity
- [ ] `tests/test_session_roundtrip.py`
  - [ ] `test_session_roundtrip_all_fields` — write → parse → assert all fields identical
  - [ ] `test_session_roundtrip_optional_fields_none` — None fields omitted and parse back as None

### Gap 2: Active file concurrent-write simulation
- [x] `tests/test_active_file_concurrent.py`
  - [x] `test_concurrent_write_reader_never_sees_partial_slug`
  - [x] Test helper uses unique temp file names per write; no shared `active.tmp`
  - [x] Writer-thread exceptions are captured and asserted empty after join
  - [x] Running pytest produces no `PytestUnhandledThreadExceptionWarning`

### Gap 3: Partial active file read
- [x] `tests/test_active_file_concurrent.py`
  - [x] `test_partial_active_file_returns_none`

### Gap 4: org.toml change detection
- [x] Covered by D-3 tests above (`test_changed_org_warning_emitted`)

### Gap 5: Attribution cascade priority
- [x] `tests/test_collector_attr_method.py` (extend from v2.21)
  - [x] `test_timer_takes_precedence_over_ws_root`
  - [x] `test_timer_takes_precedence_over_git`
  - [x] `test_ws_root_takes_precedence_over_git`

### Gap 6: Plist XML injection
- [x] Covered by D-4 tests above

### Gap 7: Gemini session-id 8-char prefix collision
- [x] `tests/test_gemini_prefix_collision.py`
  - [x] `test_prefix_collision_sessions_attributed_independently`

### Gap 8: Pricing table partial-fetch
- [x] Covered by D-5 tests above (`test_truncated_response_no_overwrite`)

### Gap 9: read_sessions tool limit parameter
- [x] `tests/test_read_sessions_limit.py`
  - [x] `test_large_limit_completes_in_time` — 10 000-line log, assert < 2s
  - [x] `test_large_limit_no_oom` — memory usage stays within reasonable bound

### Gap 10: _validate_base_url with localhost variants
- [x] `tests/test_base_url_validation.py` (extend from v2.20)
  - [x] `test_validate_127_0_0_1_accepted`
  - [x] `test_validate_localhost_accepted`
  - [x] `test_validate_ipv6_loopback_accepted`
  - [x] `test_validate_127_0_0_1_with_port_accepted`
  - [x] `test_validate_localhost_with_port_accepted`
  - [x] `test_validate_private_ip_rejected`

## Quality
- [x] Run full test suite — all passing
- [x] Run mypy — no new errors
- [x] Run ruff — no new errors
- [x] Run `ruff format --check .` — no formatting drift
