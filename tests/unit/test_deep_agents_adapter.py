from types import SimpleNamespace

import pytest

from agntid.adapters.base import assert_adapter_identity
from agntid.adapters.langchain_deep_agents import DeepAgentsAdapter
from agntid.context import ExecutionPlan, PlannedAction, arguments_digest


def test_deep_agents_adapter_emits_root_context_and_constraints():
    adapter = DeepAgentsAdapter()
    event = SimpleNamespace(
        prompt="Get LIVE-42. Do not send a notification.",
        prior_user_prompts=(),
        conversation_summary="",
        active_constraints=(),
        revoked_intent_ids=(),
        entity_references={},
        organization_id=None,
        user_roles=(),
        thread_id="thread-1",
        execution_plan=ExecutionPlan(
            plan_id="plan-1",
            actions=(PlannedAction("lookup", "Lookup ticket"),),
        ),
    )

    assert_adapter_identity(adapter)
    context = adapter.execution_context(event, task_id="task-1", agent_id="root")

    assert context.framework.name == "langchain-deep-agents"
    assert context.conversation.active_constraints == (
        "Do not send a notification.",
    )
    assert context.execution_plan.plan_id == "plan-1"


def test_deep_agents_adapter_does_not_promote_prior_turn_constraints():
    adapter = DeepAgentsAdapter()
    event = SimpleNamespace(
        prompt="If LIVE-42 is critical, send a notification.",
        prior_user_prompts=(
            "Get LIVE-42. Do not send a notification for this request.",
        ),
        conversation_summary="",
        active_constraints=(),
        revoked_intent_ids=(),
        entity_references={},
        organization_id=None,
        user_roles=(),
        thread_id="thread-1",
        execution_plan=None,
    )

    context = adapter.execution_context(event, task_id="task-2", agent_id="root")

    assert "Do not send a notification" in context.conversation.summary
    assert context.conversation.active_constraints == ()


def test_deep_agents_adapter_preserves_explicit_persistent_constraints():
    adapter = DeepAgentsAdapter()
    event = SimpleNamespace(
        prompt="If LIVE-42 is critical, send a notification.",
        prior_user_prompts=("Get LIVE-42. Do not modify it.",),
        conversation_summary="",
        active_constraints=("Never modify production tickets.",),
        revoked_intent_ids=(),
        entity_references={},
        organization_id=None,
        user_roles=(),
        thread_id="thread-1",
        execution_plan=None,
    )

    context = adapter.execution_context(event, task_id="task-3", agent_id="root")

    assert context.conversation.active_constraints == (
        "Never modify production tickets.",
    )


def test_deep_agents_adapter_extracts_delegated_prompt_from_state():
    adapter = DeepAgentsAdapter()
    policy = SimpleNamespace(
        acting_agent_id="researcher",
        tool_allowlist=("get_ticket",),
        agntid_tool_id_map={"get_ticket": "tickets.get"},
    )
    context = SimpleNamespace(
        task_id="task-1",
        agent_id="root",
        prompt="Get LIVE-42 and summarize it.",
        delegation_policies={"researcher": policy},
        approval_for=lambda *_: None,
    )
    runtime = SimpleNamespace(
        config={"metadata": {"lc_agent_name": "researcher"}},
        state={"messages": [{"role": "user", "content": "Read LIVE-42"}]},
    )
    request = SimpleNamespace(name="get_ticket", args={}, runtime=runtime)

    proposal = adapter.delegation_for_request(request=request, context=context)

    assert proposal is not None
    assert proposal.acting_agent_id == "researcher"
    assert proposal.delegated_intent == "Read LIVE-42"
    assert proposal.tool_allowlist == ("tickets.get",)


def test_deep_agents_adapter_observes_native_task_before_business_tool():
    policy = SimpleNamespace(
        acting_agent_id="researcher:v1",
        tool_allowlist=("get_ticket",),
        agntid_tool_id_map={"get_ticket": "tickets.get"},
    )
    context = SimpleNamespace(
        task_id="task-1",
        agent_id="root:v1",
        delegation_policies={"researcher": policy},
    )

    proposal = DeepAgentsAdapter().delegation_for_task_call(
        subagent_type="researcher",
        description="Inspect LIVE-42 only.",
        tool_call_id="framework-call-1",
        context=context,
    )

    assert proposal.framework_agent_name == "researcher"
    assert proposal.acting_agent_id == "researcher:v1"
    assert proposal.parent_agent_id == "root:v1"
    assert proposal.delegated_intent == "Inspect LIVE-42 only."
    assert proposal.tool_allowlist == ("tickets.get",)
    assert DeepAgentsAdapter().capabilities.framework_delegation_events is True


def test_named_subagent_without_trusted_policy_fails_closed():
    context = SimpleNamespace(
        task_id="task-1",
        agent_id="root",
        prompt="Get LIVE-42",
        delegation_policies={},
    )
    runtime = SimpleNamespace(
        config={"metadata": {"lc_agent_name": "untrusted-child"}},
        state={"messages": [{"role": "user", "content": "Read LIVE-42"}]},
    )
    request = SimpleNamespace(name="get_ticket", args={}, runtime=runtime)

    with pytest.raises(RuntimeError, match="no trusted AgentID delegation policy"):
        DeepAgentsAdapter().delegation_for_request(request=request, context=context)


def test_named_root_agent_without_distinct_delegated_message_remains_root():
    context = SimpleNamespace(
        task_id="task-1",
        agent_id="root",
        prompt="Get LIVE-42",
        delegation_policies={},
    )
    runtime = SimpleNamespace(
        config={"metadata": {"lc_agent_name": "root-framework-agent"}},
        state={"messages": [{"role": "user", "content": "Get LIVE-42"}]},
    )
    request = SimpleNamespace(name="get_ticket", args={}, runtime=runtime)

    assert (
        DeepAgentsAdapter().delegation_for_request(request=request, context=context)
        is None
    )


def test_delegated_framework_approval_is_bound_to_canonical_call():
    args = {"channel": "ops", "message": "LIVE-42 is critical"}
    policy = SimpleNamespace(
        acting_agent_id="notifier",
        tool_allowlist=("send_notification",),
        agntid_tool_id_map={"send_notification": "notifications.send"},
    )
    context = SimpleNamespace(
        task_id="task-1",
        agent_id="root",
        prompt="Notify on-call",
        delegation_policies={"notifier": policy},
        approval_for=lambda *_: {
            "required": True,
            "decision": "approved",
            "decision_id": "approval-1",
            "operation_id": "operation-1",
            "approver_id": "alice",
            "expires_at": "2026-08-12T08:05:00Z",
        },
    )
    runtime = SimpleNamespace(
        config={"metadata": {"lc_agent_name": "notifier"}},
        state={"messages": [{"role": "user", "content": "Send the notice"}]},
    )
    request = SimpleNamespace(name="send_notification", args=args, runtime=runtime)

    proposal = DeepAgentsAdapter().delegation_for_request(
        request=request, context=context
    )

    assert proposal is not None
    assert proposal.approval["source"] == "framework_interrupt"
    assert proposal.approval["operation_id"] == "operation-1"
    assert proposal.approval["tool_name"] == "notifications.send"
    assert proposal.approval["arguments_digest"] == arguments_digest(args)
