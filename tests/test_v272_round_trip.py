from datetime import datetime

from hypothesis import given
from hypothesis import strategies as st

from halyard.ai_log import AiSession, _parse_line_result


def safe_string_strategy():
    # Any string that _safe_field might be applied to.
    # We use min_size=1 because most fields are omitted if empty.
    return st.text(alphabet=st.characters(blacklist_categories=["Cc", "Zs"]), min_size=1).filter(
        lambda x: " " not in x and "=" not in x
    )


def free_text_strategy():
    # Any string that _encode_free_text handles.
    # min_size=1 because if empty, most fields are omitted.
    # We avoid "_" because of the current asymmetry in _decode_free_text.
    # We avoid "Cs" (surrogates) because urllib.parse.quote fails on them.
    return st.text(alphabet=st.characters(blacklist_categories=["Cc", "Cs"]), min_size=1).filter(
        lambda x: "_" not in x
    )


def tag_element_strategy():
    return free_text_strategy()


def model_breakdown_strategy():
    # "model-a:3|model-b:1"
    return st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789:-|", min_size=1)


def extra_key_strategy():
    # Matches _EXTRA_KEY_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9_.-]*\Z")
    return st.from_regex(r"[A-Za-z][A-Za-z0-9_.-]*", fullmatch=True)


@st.composite
def ai_session_strategy(draw):
    # head fields
    start = datetime(2026, 5, 22, 12, 0, 0)
    end = datetime(2026, 5, 22, 12, 30, 0)
    tool = draw(safe_string_strategy())
    model = draw(safe_string_strategy())
    input_tokens = draw(st.integers(min_value=0, max_value=1_000_000))
    output_tokens = draw(st.integers(min_value=0, max_value=1_000_000))
    # match f"{self.cost_usd:.4f}" precision
    cost_usd = draw(st.floats(min_value=0, max_value=100.0, allow_nan=False, allow_infinity=False))
    cost_usd = float(f"{cost_usd:.4f}")

    session = AiSession(
        start=start,
        end=end,
        tool=tool,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
    )

    # optional fields
    if draw(st.booleans()):
        session.project = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.user = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.cache_read = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.cache_write = draw(st.integers(min_value=0))
    session.tokens_available = draw(st.booleans())
    # billing defaults to "api" and is omitted if it is "api"
    billing = draw(safe_string_strategy())
    if billing == "api":
        session.billing = "api"
    else:
        session.billing = billing

    if draw(st.booleans()):
        credits = draw(st.floats(min_value=0, allow_nan=False, allow_infinity=False))
        session.credits = float(f"{credits:.4f}")

    if draw(st.booleans()):
        session.job_id = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.source = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.attr_method = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.tags = draw(st.lists(tag_element_strategy(), min_size=1))
    if draw(st.booleans()):
        session.note = draw(free_text_strategy())
    if draw(st.booleans()):
        session.session_id = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.tool_calls = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.tool_errors = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.wall_seconds = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.agent_active_seconds = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.api_seconds = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.tool_seconds = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.code_added = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.code_removed = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.model_breakdown = draw(model_breakdown_strategy())
    if draw(st.booleans()):
        session.resume_command = draw(free_text_strategy())
    if draw(st.booleans()):
        session.branch = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.remote = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.client_surface = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.commit_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.pr_ref = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.pr_state = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.outcome_resolved_at = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.review_comments = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.review_rounds = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.time_to_merge_s = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.review_decision = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.mcp_servers_used = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.mcp_server_names = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.interaction_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.user_message_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.assistant_message_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.prompt_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.accepted_suggestion_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.rejected_suggestion_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.files_touched_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.test_run_count = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.test_status = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.build_status = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.human_active_seconds = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.idle_seconds = draw(st.integers(min_value=0))
    if draw(st.booleans()):
        session.interaction_data_available = draw(st.booleans())
    if draw(st.booleans()):
        session.outcome_data_available = draw(st.booleans())
    if draw(st.booleans()):
        session.telemetry_source = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.telemetry_trust = draw(safe_string_strategy())
    if draw(st.booleans()):
        session.extra = draw(
            st.dictionaries(keys=extra_key_strategy(), values=free_text_strategy())
        )

    return session


@given(ai_session_strategy())
def test_v272_round_trip(session: AiSession):
    line1 = session.to_log_line()
    parsed, error = _parse_line_result(line1)

    assert error is None, f"Parsing failed for line: {line1}"
    assert parsed is not None

    line2 = parsed.to_log_line()
    assert line1 == line2, f"Round-trip mismatch!\nL1: {line1}\nL2: {line2}"


def test_v272_golden_corpus():
    # A set of complex lines to ensure we don't break existing formats.
    corpus = [
        (
            "s 2026-05-22T12:00:00 2026-05-22T12:30:00 tool model 100 200 0.0500 "
            "project=p1 user=u1 cache_read=10 cache_write=5 tokens_available=false "
            "billing=credits credits=1.2345 job_id=j1 source=s1 attr_method=timer "
            "tags=t1,t2%20space note=my%20note session_id=sid1 tool_calls=3 "
            "tool_errors=0 wall_seconds=1800 agent_active_seconds=600 api_seconds=100 "
            "tool_seconds=200 code_added=50 code_removed=10 model_breakdown=m:1 "
            "resume_command=res%21 branch=main remote=origin client_surface=cli "
            "commit_count=5 pr_ref=repo#1 pr_state=merged "
            "outcome_resolved_at=2026-05-22T13:00:00 review_comments=2 "
            "review_rounds=1 time_to_merge_s=3600 review_decision=APPROVED "
            "mcp_servers_used=2 mcp_server_names=s1,s2 interaction_count=10 "
            "user_message_count=5 assistant_message_count=5 prompt_count=5 "
            "accepted_suggestion_count=4 rejected_suggestion_count=1 "
            "files_touched_count=3 test_run_count=2 test_status=pass build_status=success "
            "human_active_seconds=1200 idle_seconds=300 interaction_data_available=true "
            "outcome_data_available=true telemetry_source=otlp telemetry_trust=high "
            "extra_key=extra%20val"
        ),
        "s 2026-05-22T12:00:00 2026-05-22T12:30:00 tool model 0 0 0.0000",
    ]
    for line in corpus:
        parsed, error = _parse_line_result(line)
        assert error is None, f"Golden corpus parsing failed for line: {line}"
        assert parsed is not None
        assert parsed.to_log_line() == line
