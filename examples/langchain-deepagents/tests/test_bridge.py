import json
from types import SimpleNamespace

import pytest
from agntid import ExecutionPlan, PlannedAction
from agntid.task import DELEGATION_CLOSE_TOOL, TASK_CLOSE_TOOL
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from agntid_deepagents_poc.bridge import (
    APPROVAL_EVIDENCE_ARGUMENT,
    AgntidBridge,
    CORRELATION_ARGUMENT,
    DELEGATION_CORRELATION_ARGUMENT,
    SERVER_NAME,
    identity_interceptor,
)
from agntid_deepagents_poc.adapter import DeepAgentsAdapter
from agntid_deepagents_poc.identity import DelegationPolicy, InvocationContext


def test_bridge_does_not_call_unsupported_session_delete_on_close():
    bridge = AgntidBridge("http://agntid.test/mcp")

    assert bridge._client.connections[SERVER_NAME]["terminate_on_close"] is False


@pytest.mark.asyncio
async def test_close_task_mirrors_server_not_attempted_state_locally():
    class CloseTool:
        async def ainvoke(self, arguments):
            assert arguments == {"task_id": "task-1"}
            return SimpleNamespace(
                structuredContent={"ok": True, "changed": True},
                content=[],
            )

    bridge = AgntidBridge.__new__(AgntidBridge)
    bridge._tools = {TASK_CLOSE_TOOL: CloseTool()}
    context = InvocationContext(
        agent_id="root:v1",
        user_id="alice",
        prompt="Notify if critical",
        task_id="task-1",
        execution_plan=ExecutionPlan(
            plan_id="plan-1",
            actions=(
                PlannedAction(
                    action_id="notify",
                    title="Send notification",
                    status="planned",
                    requirement="conditional",
                    condition="Ticket is critical",
                    condition_status="met",
                ),
            ),
        ),
    )

    await bridge.close_task(context)

    assert context.plan_action_states["notify"] == "not_attempted"


@pytest.mark.asyncio
async def test_close_delegations_preserves_failure_status_and_reason():
    calls = []

    class CloseDelegationTool:
        async def ainvoke(self, arguments):
            calls.append(arguments)
            return SimpleNamespace(structuredContent={"ok": True}, content=[])

    bridge = AgntidBridge.__new__(AgntidBridge)
    bridge._tools = {DELEGATION_CLOSE_TOOL: CloseDelegationTool()}
    context = InvocationContext(
        agent_id="root:v1",
        user_id="alice",
        prompt="Investigate LIVE-42",
        task_id="task-1",
        open_delegations={
            "incident": {"delegation_id": "delegation-1"},
        },
    )

    await bridge.close_delegations(
        context,
        status="failed",
        reason="Agent execution failed: ExceptionGroup",
    )

    assert calls == [
        {
            "task_id": "task-1",
            "delegation_id": "delegation-1",
            "status": "failed",
            "reason": "Agent execution failed: ExceptionGroup",
        }
    ]
    assert context.open_delegations == {}


@pytest.mark.asyncio
async def test_interceptor_overwrites_model_supplied_task_id_and_captures_audit():
    context = InvocationContext(
        agent_id="trusted-agent",
        user_id="trusted-user",
        prompt="Add 11 and 22",
        task_id="trusted-task",
    )
    request = MCPToolCallRequest(
        name="demo_add_numbers",
        args={"first_number": 11, "second_number": 22, CORRELATION_ARGUMENT: "forged"},
        server_name="agntid",
        runtime=SimpleNamespace(context=context),
    )
    seen = {}
    envelope = {
        "__agntid_execution_flow": {
            "status": "success",
            "tool_name": "demo.add_numbers",
            "session_id": "trusted-task",
        },
        "__agntid_result": {"result": 33},
    }

    async def handler(modified):
        seen.update(modified.args)
        return SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps(envelope))],
            structuredContent=None,
        )

    await identity_interceptor(request, handler)

    assert seen[CORRELATION_ARGUMENT] == "trusted-task"
    assert context.audit_events[0]["agent_id"] == "trusted-agent"
    assert context.audit_events[0]["user_id"] == "trusted-user"
    assert "state_keys" in context.transport_events[0]["bridge_only"]
    assert "message_count" in context.transport_events[0]["bridge_only"]
    assert context.transport_events[0]["received_from_agntid"]["is_error"] is False


@pytest.mark.asyncio
async def test_interceptor_rejects_unattributed_graph_tool_call():
    request = MCPToolCallRequest(
        name="demo_add_numbers",
        args={"first_number": 1, "second_number": 2},
        server_name="agntid",
        runtime=SimpleNamespace(context=None),
    )

    async def handler(_request):
        raise AssertionError("handler must not run")

    with pytest.raises(RuntimeError, match="InvocationContext"):
        await identity_interceptor(request, handler)


@pytest.mark.asyncio
async def test_interceptor_opens_delegation_and_overwrites_forged_child_context():
    context = InvocationContext(
        agent_id="root-agent:v1",
        user_id="trusted-user",
        prompt="Get LIVE-42 and notify on-call",
        task_id="trusted-task",
        delegation_policies={
            "incident-investigator": DelegationPolicy(
                acting_agent_id="incident-investigator:v1",
                tool_allowlist=("demo_get_ticket",),
            )
        },
    )
    request = MCPToolCallRequest(
        name="demo_get_ticket",
        args={
            "ticket_id": "LIVE-42",
            CORRELATION_ARGUMENT: "forged-task",
            DELEGATION_CORRELATION_ARGUMENT: "forged-delegation",
        },
        server_name="agntid",
        runtime=SimpleNamespace(
            context=context,
            config={"metadata": {"lc_agent_name": "incident-investigator"}},
            state={"messages": [HumanMessage(content="Read ticket LIVE-42 only")]},
        ),
    )

    class FakeBridge:
        adapter = DeepAgentsAdapter()

        def __init__(self):
            self.proposals = []

        async def ensure_delegation(self, _context, proposal):
            self.proposals.append(proposal)

    bridge = FakeBridge()
    seen = {}

    async def handler(modified):
        seen.update(modified.args)
        return SimpleNamespace(content=[], structuredContent=None)

    await identity_interceptor(request, handler, bridge=bridge)

    assert seen[CORRELATION_ARGUMENT] == "trusted-task"
    assert seen[DELEGATION_CORRELATION_ARGUMENT] != "forged-delegation"
    assert seen[DELEGATION_CORRELATION_ARGUMENT] == bridge.proposals[0].delegation_id
    assert context.framework_events[0]["available_to_bridge"]["delegated_intent"] == (
        "Read ticket LIVE-42 only"
    )


@pytest.mark.asyncio
async def test_agntid_review_interrupt_resumes_once_with_bound_approval(monkeypatch):
    context = InvocationContext(
        agent_id="root-agent:v1",
        user_id="trusted-user",
        prompt="Send the approved incident notice",
        task_id="trusted-task",
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
    request = MCPToolCallRequest(
        name="demo_send_notification",
        args=args,
        server_name="agntid",
        runtime=SimpleNamespace(
            context=context,
            config={"metadata": {"lc_agent_name": "communications-specialist"}},
            state={"messages": [HumanMessage(content="Send the incident notice")]},
        ),
    )

    class FakeBridge:
        adapter = DeepAgentsAdapter()

        def __init__(self):
            self.proposals = []

        async def ensure_delegation(self, _context, proposal):
            self.proposals.append(proposal)

    bridge = FakeBridge()
    waiting = {
        "__agntid_execution_flow": {"status": "waiting"},
        "__agntid_policy_decision": {
            "allowed": False,
            "correlation_id": "operation-1",
            "intent_validation": {
                "status": "review_required",
                "verdict": "review_required",
                "review": {
                    "review_id": "review-1",
                    "outcome": "review_required",
                    "status": "pending",
                    "resolution_code": "APPROVAL_REQUIRED",
                },
            },
        },
    }
    success = {
        "__agntid_execution_flow": {"status": "success"},
        "__agntid_policy_decision": {"allowed": True},
        "__agntid_result": {"sent": True},
    }
    calls = []

    async def handler(modified):
        calls.append(dict(modified.args))
        payload = waiting if len(calls) == 1 else success
        return SimpleNamespace(structuredContent=payload, content=[], isError=False)

    def approve_interrupt(value):
        assert value["review_source"] == "agntid_policy_review"
        assert value["review"]["operation_id"] == "operation-1"
        context.record_approval(
            tool_name="demo_send_notification",
            arguments=args,
            decision="approved",
            decision_id="approval-1",
            operation_id=value["review"]["operation_id"],
            source="agntid_review_via_framework_interrupt",
        )
        return {"decisions": [{"type": "approve"}]}

    monkeypatch.setattr("agntid_deepagents_poc.bridge.interrupt", approve_interrupt)

    response = await identity_interceptor(request, handler, bridge=bridge)

    assert response.structuredContent["__agntid_result"] == {"sent": True}
    assert len(calls) == 2
    assert APPROVAL_EVIDENCE_ARGUMENT not in calls[0]
    assert calls[1][APPROVAL_EVIDENCE_ARGUMENT]["decision_id"] == "approval-1"
    assert calls[1][APPROVAL_EVIDENCE_ARGUMENT]["operation_id"] == "operation-1"
    assert len(bridge.proposals) == 2
    assert bridge.proposals[0].approval is None
    assert bridge.proposals[1].approval["decision_id"] == "approval-1"
    assert context.transport_events[-1]["phase"] == "agntid_review_resume"
