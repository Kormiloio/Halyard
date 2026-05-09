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

- [ ] Add `_org_hash_path()` helper returning `~/.halyard/org-hash.txt`
- [ ] Implement `_check_org_hash(content: bytes) -> None`
  - Compute SHA-256 of content
  - Read existing hash from `_org_hash_path()` if present
  - If hash differs: print warning to stderr; write new hash
  - If hash matches: no-op
  - If no stored hash (first run): write hash silently
- [ ] Call `_check_org_hash()` in the org.toml load path
- [ ] `tests/test_org_hash.py`
  - [ ] `test_first_run_no_warning` — no hash file → no warning, hash written
  - [ ] `test_unchanged_org_no_warning` — same content → no warning
  - [ ] `test_changed_org_warning_emitted` — changed content → warning printed
  - [ ] `test_changed_org_hash_updated` — new hash stored after change

## D-5: Pricing table hash pinning

- [ ] Add `_pricing_hash_path()` helper returning `~/.halyard/pricing-hash.txt`
- [ ] Wrap pricing table HTTP fetch to verify Content-Length / completeness
- [ ] Implement `_check_pricing_hash(body: bytes) -> bool`
  - Compute SHA-256 of body
  - Read existing hash from `_pricing_hash_path()` if present
  - Return True (hashes match) or False (differ / no stored hash)
- [ ] On hash mismatch: print warning; accept for current session but do not
  persist new hash
- [ ] On truncated response: abort; do not update local table or hash
- [ ] `tests/test_pricing_hash.py`
  - [ ] `test_first_fetch_no_warning` — no stored hash → accept silently
  - [ ] `test_matching_hash_no_warning` — same body → no warning
  - [ ] `test_changed_pricing_table_warning` — changed body → warning printed
  - [ ] `test_truncated_response_no_overwrite` — incomplete response → local table unchanged
  - [ ] `test_truncated_response_hash_not_updated` — incomplete response → hash file unchanged

---

## Test coverage gaps

### Gap 1: Session round-trip fidelity
- [ ] `tests/test_session_roundtrip.py`
  - [ ] `test_session_roundtrip_all_fields` — write → parse → assert all fields identical
  - [ ] `test_session_roundtrip_optional_fields_none` — None fields omitted and parse back as None

### Gap 2: Active file concurrent-write simulation
- [ ] `tests/test_active_file_concurrent.py`
  - [ ] `test_concurrent_write_reader_never_sees_partial_slug`

### Gap 3: Partial active file read
- [ ] `tests/test_active_file_concurrent.py`
  - [ ] `test_partial_active_file_returns_none`

### Gap 4: org.toml change detection
- [ ] Covered by D-3 tests above (`test_changed_org_warning_emitted`)

### Gap 5: Attribution cascade priority
- [ ] `tests/test_collector_attr_method.py` (extend from v2.21)
  - [ ] `test_timer_takes_precedence_over_ws_root`
  - [ ] `test_timer_takes_precedence_over_git`
  - [ ] `test_ws_root_takes_precedence_over_git`

### Gap 6: Plist XML injection
- [ ] Covered by D-4 tests above

### Gap 7: Gemini session-id 8-char prefix collision
- [ ] `tests/test_gemini_prefix_collision.py`
  - [ ] `test_prefix_collision_sessions_attributed_independently`

### Gap 8: Pricing table partial-fetch
- [ ] Covered by D-5 tests above (`test_truncated_response_no_overwrite`)

### Gap 9: read_sessions tool limit parameter
- [ ] `tests/test_read_sessions_limit.py`
  - [ ] `test_large_limit_completes_in_time` — 10 000-line log, assert < 2s
  - [ ] `test_large_limit_no_oom` — memory usage stays within reasonable bound

### Gap 10: _validate_base_url with localhost variants
- [ ] `tests/test_base_url_validation.py` (extend from v2.20)
  - [ ] `test_validate_127_0_0_1_accepted`
  - [ ] `test_validate_localhost_accepted`
  - [ ] `test_validate_ipv6_loopback_accepted`
  - [ ] `test_validate_127_0_0_1_with_port_accepted`
  - [ ] `test_validate_localhost_with_port_accepted`
  - [ ] `test_validate_private_ip_rejected`

## Quality
- [ ] Run full test suite — all passing
- [ ] Run mypy — no new errors
- [ ] Run ruff — no new errors
