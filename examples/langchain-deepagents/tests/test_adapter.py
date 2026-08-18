from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from agntid_deepagents_poc.adapter import DeepAgentsAdapter
from agntid_deepagents_poc.identity import DelegationPolicy, InvocationContext
from agntid.context import arguments_digest


def test_root_context_contains_framework_thread_and_bounded_constraints():
    context = InvocationContext(
        agent_id="operations-supervisor:v1",
        user_id="alice",
        prompt="Send the incident notice. Do not export payroll records.",
        task_id="task-1",
        thread_id="thread-1",
        prior_user_prompts=("Use ticket LIVE-42.",),
    )

    payload = DeepAgentsAdapter().execution_context(context).to_dict()

    assert payload["version"] == "1.0"
    assert payload["framework"]["name"] == "langchain-deep-agents"
    assert payload["thread_id"] == "thread-1"
    assert payload["root_task_id"] == "task-1"
    assert payload["root_agent_id"] == "operations-supervisor:v1"
    assert "Do not export payroll records." in payload["conversation"][
        "active_constraints"
    ]
    assert "LIVE-42" in payload["conversation"]["summary"]


def test_subagent_runtime_becomes_canonical_delegation():
    context = InvocationContext(
        agent_id="operations-supervisor:v1",
        user_id="alice",
        prompt="Get LIVE-42 and notify the on-call engineer",
        task_id="task-1",
        delegation_policies={
            "incident-investigator": DelegationPolicy(
                acting_agent_id="incident-investigator:v1",
                tool_allowlist=("demo_get_ticket",),
                agntid_tool_id_map={"demo_get_ticket": "demo.get_ticket"},
            )
        },
    )
    request = MCPToolCallRequest(
        name="demo_get_ticket",
        args={"ticket_id": "LIVE-42"},
        server_name="agntid",
        runtime=SimpleNamespace(
            context=context,
            config={"metadata": {"lc_agent_name": "incident-investigator"}},
            state={"messages": [HumanMessage(content="Read ticket LIVE-42 only")]},
        ),
    )

    proposal = DeepAgentsAdapter().delegation_for_request(
        request=request, context=context
    )

    assert proposal is not None
    assert proposal.acting_agent_id == "incident-investigator:v1"
    assert proposal.parent_agent_id == "operations-supervisor:v1"
    assert proposal.delegated_intent == "Read ticket LIVE-42 only"
    assert proposal.tool_allowlist == ("demo.get_ticket",)


def test_unknown_child_agent_fails_closed():
    context = InvocationContext(
        agent_id="operations-supervisor:v1",
        user_id="alice",
        prompt="Get LIVE-42",
        delegation_policies={
            "incident-investigator": DelegationPolicy(
                acting_agent_id="incident-investigator:v1",
                tool_allowlist=("demo_get_ticket",),
            )
        },
    )
    request = MCPToolCallRequest(
        name="demo_get_ticket",
        args={"ticket_id": "LIVE-42"},
        server_name="agntid",
        runtime=SimpleNamespace(
            context=context,
            config={"metadata": {"lc_agent_name": "untrusted-child"}},
            state={"messages": [HumanMessage(content="Read LIVE-42")]},
        ),
    )

    with pytest.raises(RuntimeError, match="no trusted AgentID delegation policy"):
        DeepAgentsAdapter().delegation_for_request(request=request, context=context)


def test_framework_approval_is_bound_to_canonical_tool_and_arguments():
    context = InvocationContext(
        agent_id="operations-supervisor:v1",
        user_id="alice",
        prompt="Notify the on-call engineer",
        task_id="task-1",
        delegation_policies={
            "communications-specialist": DelegationPolicy(
                acting_agent_id="communications-specialist:v1",
                tool_allowlist=("demo_send_notification",),
                agntid_tool_id_map={
                    "demo_send_notification": "demo.send_notification"
                },
            )
        },
    )
    args = {"channel": "ops", "message": "LIVE-42 is critical"}
    context.record_approval(
        tool_name="demo_send_notification",
        arguments=args,
        decision="approved",
        decision_id="approval-1",
        operation_id="operation-1",
    )
    request = MCPToolCallRequest(
        name="demo_send_notification",
        args=args,
        server_name="agntid",
        runtime=SimpleNamespace(
            context=context,
            config={"metadata": {"lc_agent_name": "communications-specialist"}},
            state={"messages": [HumanMessage(content="Send the approved notice")]},
        ),
    )

    proposal = DeepAgentsAdapter().delegation_for_request(request=request, context=context)

    assert proposal is not None
    approval = proposal.approval
    assert approval["source"] == "framework_interrupt"
    assert approval["operation_id"] == "operation-1"
    assert approval["tool_name"] == "demo.send_notification"
    assert approval["arguments_digest"] == arguments_digest(args)
    assert approval["expires_at"]
