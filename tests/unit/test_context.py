from agntid.context import (
    ConversationContext,
    DelegatedIntent,
    DelegationContext,
    ExecutionContext,
    FrameworkInfo,
    extract_explicit_constraints,
)


def test_execution_context_serializes_canonical_wire_shape():
    context = ExecutionContext(
        framework=FrameworkInfo(
            name="test-framework",
            adapter_version="1.0.0",
            capabilities=("conversation_summary",),
        ),
        thread_id="thread-1",
        turn_id="turn-1",
        root_task_id="task-1",
        root_agent_id="root-agent",
        conversation=ConversationContext(
            summary="Earlier the user selected LIVE-42.",
            active_constraints=("Do not notify anyone.",),
        ),
    )

    assert context.to_dict()["framework"]["name"] == "test-framework"
    assert context.to_dict()["conversation"]["active_constraints"] == [
        "Do not notify anyone."
    ]


def test_delegation_context_serializes_lineage_and_bounded_intent():
    context = DelegationContext(
        delegation_id="delegation-1",
        parent_agent_id="root-agent",
        acting_agent_id="researcher",
        delegated_intent=DelegatedIntent(text="Read LIVE-42"),
        tool_allowlist=("tickets.get",),
    )

    payload = context.to_dict()
    assert payload["delegation_id"] == "delegation-1"
    assert payload["delegated_intent"]["text"] == "Read LIVE-42"
    assert payload["tool_allowlist"] == ["tickets.get"]


def test_explicit_constraints_exclude_conditional_negative_branches():
    constraints = extract_explicit_constraints(
        "If and only if it is critical, notify operations. "
        "Otherwise, do not notify anyone. Do not update the ticket."
    )

    assert constraints == ("Do not update the ticket.",)


def test_explicit_constraints_exclude_inline_conditional_prohibitions():
    constraints = extract_explicit_constraints(
        "Do not notify unless the verified severity is critical."
    )

    assert constraints == ()
