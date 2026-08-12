from types import SimpleNamespace

import pytest

from agntid.adapters.base import assert_adapter_identity
from agntid.adapters.langchain_deep_agents import DeepAgentsAdapter


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
    )

    assert_adapter_identity(adapter)
    context = adapter.execution_context(event, task_id="task-1", agent_id="root")

    assert context.framework.name == "langchain-deep-agents"
    assert context.conversation.active_constraints == (
        "Do not send a notification.",
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
