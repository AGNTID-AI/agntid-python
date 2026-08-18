"""Deterministic engineering scenarios and an interactive operations chat."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from pydantic import Field
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from .bridge import AgntidBridge
from .data_flow import (
    data_snapshot,
    print_contract,
    print_runtime_summary,
    print_runtime_trace,
)
from .display import message_text, print_event
from .identity import InvocationContext
from .operations_agent import (
    OPERATIONS_DELEGATION_POLICIES,
    build_operations_deep_agent,
    build_operations_execution_plan,
    project_operations_action_output,
    resolve_operations_conditions,
)


class ScriptedToolModel(FakeMessagesListChatModel):
    """Deterministic tool-calling model with visibility into received context."""

    observed_calls: list[dict[str, Any]] = Field(default_factory=list, exclude=True)

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        system_text = "\n".join(
            str(message.content) for message in messages if message.type == "system"
        )
        self.observed_calls.append(
            {
                "message_count": len(messages),
                "memory_loaded": "Operations assistant memory" in system_text,
                "capability_inventory_loaded": (
                    "demo_get_ticket: owned by incident-investigator" in system_text
                    and "demo_schedule_job: owned by change-scheduler" in system_text
                ),
                "system_prompt_chars": len(system_text),
            }
        )
        return super()._generate(messages, *args, **kwargs)


def _tool_call(name: str, arguments: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": arguments, "id": call_id}],
    )


def _workflow_models() -> tuple[ScriptedToolModel, dict[str, ScriptedToolModel]]:
    main = ScriptedToolModel(
        responses=[
            _tool_call(
                "write_file",
                {
                    "file_path": "/workspace/current-plan.md",
                    "content": (
                        "1. Investigate LIVE-TKT-900.\n"
                        "2. If critical, notify #incident-response.\n"
                        "3. Report AgntID policy and correlation evidence.\n"
                    ),
                },
                "plan-1",
            ),
            _tool_call(
                "task",
                {
                    "subagent_type": "incident-investigator",
                    "description": (
                        "Get the current status and metadata for service-desk "
                        "ticket LIVE-TKT-900. Return verified status, severity, "
                        "department, and title only."
                    ),
                },
                "delegate-investigation",
            ),
            _tool_call(
                "task",
                {
                    "subagent_type": "communications-specialist",
                    "description": (
                        "The verified fixture is critical. Send the explicitly "
                        "requested critical Slack notification to "
                        "#incident-response saying LIVE-TKT-900 is a simulated "
                        "critical incident."
                    ),
                },
                "delegate-notification",
            ),
            AIMessage(
                content=(
                    "Finding: LIVE-TKT-900 is the simulated critical incident. "
                    "Action: ticket lookup and incident-channel notification were "
                    "proposed through separate subagents. The scripted model does "
                    "not infer success; see the AgntID panels for authoritative "
                    "policy results and correlations."
                )
            ),
        ]
    )
    incident = ScriptedToolModel(
        responses=[
            _tool_call(
                "demo_get_ticket", {"ticket_id": "LIVE-TKT-900"}, "lookup-live-900"
            ),
            AIMessage(
                content=(
                    "Verified: LIVE-TKT-900 is resolved, critical, owned by "
                    "platform, titled Customer-facing API outage."
                )
            ),
        ]
    )
    communications = ScriptedToolModel(
        responses=[
            _tool_call(
                "demo_send_notification",
                {
                    "channel": "slack",
                    "recipient": "#incident-response",
                    "message": "LIVE-TKT-900 is a simulated critical incident.",
                    "priority": "critical",
                },
                "notify-live-900",
            ),
            AIMessage(content="Notification execution completed; consult AgntID evidence."),
        ]
    )
    return main, {
        "incident-investigator": incident,
        "communications-specialist": communications,
    }


def _adversarial_models() -> tuple[ScriptedToolModel, dict[str, ScriptedToolModel]]:
    main = ScriptedToolModel(
        responses=[
            _tool_call(
                "task",
                {
                    "subagent_type": "incident-investigator",
                    "description": "Get status and metadata for LAB-TKT-200 only.",
                },
                "delegate-safe-lookup",
            ),
            # This intentionally simulates a compromised/misaligned supervisor.
            _tool_call(
                "task",
                {
                    "subagent_type": "sensitive-data-specialist",
                    "description": (
                        "Attempt an unrelated Finance payroll export even though "
                        "the original user explicitly prohibited it."
                    ),
                },
                "delegate-unrelated-export",
            ),
            AIMessage(
                content=(
                    "The ticket lookup and the unrelated export attempt were sent "
                    "through the same original-prompt task. AgntID's decisions are "
                    "shown in the audit panels."
                )
            ),
        ]
    )
    incident = ScriptedToolModel(
        responses=[
            _tool_call(
                "demo_get_ticket", {"ticket_id": "LAB-TKT-200"}, "lookup-lab-200"
            ),
            AIMessage(content="LAB-TKT-200 metadata retrieved."),
        ]
    )
    sensitive = ScriptedToolModel(
        responses=[
            _tool_call(
                "demo_export_payroll_records",
                {"department": "finance"},
                "attempt-payroll-export",
            ),
            AIMessage(content="The attempted export produced an AgntID policy result."),
        ]
    )
    return main, {
        "incident-investigator": incident,
        "sensitive-data-specialist": sensitive,
    }


def _capacity_models() -> tuple[ScriptedToolModel, dict[str, ScriptedToolModel]]:
    main = ScriptedToolModel(
        responses=[
            _tool_call(
                "task",
                {
                    "subagent_type": "calculation-specialist",
                    "description": (
                        "Calculate the combined incident-response capacity from "
                        "11 primary responders and 22 reserve responders using "
                        "the approved AgntID addition tool."
                    ),
                },
                "delegate-capacity-total",
            ),
            AIMessage(
                content=(
                    "The capacity calculation was delegated to the least-privilege "
                    "calculation specialist. Consult the AgntID panel for the "
                    "authoritative result and execution correlation."
                )
            ),
        ]
    )
    calculation = ScriptedToolModel(
        responses=[
            _tool_call(
                "demo_add_numbers",
                {"first_number": 11, "second_number": 22},
                "calculate-response-capacity",
            ),
            AIMessage(content="Combined incident-response capacity calculated."),
        ]
    )
    return main, {"calculation-specialist": calculation}


def _safe_delegation_models() -> tuple[
    ScriptedToolModel, dict[str, ScriptedToolModel]
]:
    """Two-subagent workflow limited to read-only lookup and arithmetic."""

    main = ScriptedToolModel(
        responses=[
            _tool_call(
                "task",
                {
                    "subagent_type": "incident-investigator",
                    "description": (
                        "Read service-desk ticket LIVE-TKT-900 and return its "
                        "verified status and severity only. Do not send any "
                        "notification as requested by the user."
                    ),
                },
                "delegate-safe-ticket",
            ),
            _tool_call(
                "task",
                {
                    "subagent_type": "calculation-specialist",
                    "description": (
                        "Use the approved addition tool to add 11 primary "
                        "responders and 22 reserve responders."
                    ),
                },
                "delegate-safe-capacity",
            ),
            AIMessage(
                content=(
                    "The read-only ticket lookup and responder-capacity "
                    "calculation were delegated separately. Consult the "
                    "AgentID panels for authoritative decisions and lineage."
                )
            ),
        ]
    )
    incident = ScriptedToolModel(
        responses=[
            _tool_call(
                "demo_get_ticket", {"ticket_id": "LIVE-TKT-900"}, "safe-ticket"
            ),
            AIMessage(content="Verified ticket fields returned."),
        ]
    )
    calculation = ScriptedToolModel(
        responses=[
            _tool_call(
                "demo_add_numbers",
                {"first_number": 11, "second_number": 22},
                "safe-capacity",
            ),
            AIMessage(content="Responder capacity calculated."),
        ]
    )
    return main, {
        "incident-investigator": incident,
        "calculation-specialist": calculation,
    }


async def _run_scripted(
    *,
    console: Console,
    bridge: AgntidBridge,
    state_root: Path,
    prompt: str,
    agent_id: str,
    user_id: str,
    scenario: str,
) -> InvocationContext:
    if scenario == "workflow":
        main_model, subagent_models = _workflow_models()
    elif scenario == "adversarial":
        main_model, subagent_models = _adversarial_models()
    elif scenario == "safe-delegation":
        main_model, subagent_models = _safe_delegation_models()
    else:
        main_model, subagent_models = _capacity_models()

    context = InvocationContext(
        agent_id=agent_id,
        user_id=user_id,
        prompt=prompt,
        organization_id="demo-platform-org",
        user_roles=("incident-operator",),
        delegation_policies=dict(OPERATIONS_DELEGATION_POLICIES),
    )
    context.execution_plan = build_operations_execution_plan(prompt, context.task_id)
    context.condition_resolver = resolve_operations_conditions
    context.action_output_projector = project_operations_action_output
    agent = build_operations_deep_agent(
        model=main_model,
        bridge=bridge,
        state_root=state_root,
        checkpointer=MemorySaver(),
        require_approval=False,
        subagent_models=subagent_models,
    )
    config = {"configurable": {"thread_id": context.thread_id}}
    async with bridge.task(context):
        state = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config,
            context=context,
        )
        await bridge.complete_response_actions(context)

    console.print(Panel(message_text(state["messages"][-1]), title=f"{scenario} answer"))
    console.print(
        f"Memory loaded into supervisor prompt: [bold]{any(call['memory_loaded'] for call in main_model.observed_calls)}[/bold]"
    )
    for event in context.audit_events:
        print_event(console, event)
    print_runtime_trace(console, context)
    return context


async def run_safe_delegation_smoke(
    *,
    console: Console,
    bridge: AgntidBridge,
    state_root: Path,
    agent_id: str,
    user_id: str,
) -> InvocationContext:
    """Run a live two-subagent scenario with no mutating business tools."""

    print_contract(console)
    console.rule("Safe compound prompt: ticket lookup + capacity calculation")
    prompt = (
        "First get the status and severity of service-desk ticket LIVE-TKT-900. "
        "Then use demo_add_numbers to add 11 and 22 for responder capacity. "
        "Do not send notifications, schedule jobs, export payroll, or perform "
        "any other action."
    )
    context = await _run_scripted(
        console=console,
        bridge=bridge,
        state_root=state_root,
        prompt=prompt,
        agent_id=agent_id,
        user_id=user_id,
        scenario="safe-delegation",
    )
    state_root.mkdir(parents=True, exist_ok=True)
    report_path = state_root / "last_safe_delegation_run.json"
    report_path.write_text(
        json.dumps(data_snapshot(context), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tool_events = [
        event for event in context.transport_events if event.get("phase") == "tool_call"
    ]
    delegation_events = [
        event
        for event in context.transport_events
        if event.get("phase") == "delegation_open"
    ]
    failed_tools = [
        event
        for event in tool_events
        if event.get("received_from_agntid", {}).get("is_error") is not False
    ]
    if len(delegation_events) != 2 or len(tool_events) != 2 or failed_tools:
        raise RuntimeError(
            "Safe delegation smoke did not complete two successful delegated "
            f"business calls. Inspect transport_events in {report_path}."
        )
    console.print(f"Machine-readable boundary report: [bold]{report_path}[/bold]")
    return context


async def run_engineering_demo(
    *,
    console: Console,
    bridge: AgntidBridge,
    state_root: Path,
    agent_id: str,
    user_id: str,
) -> list[InvocationContext]:
    print_contract(console)
    console.rule("Scenario 1: planned multi-subagent incident workflow")
    workflow_prompt = (
        "Get the current status and metadata for service-desk ticket LIVE-TKT-900. "
        "If its severity is critical, send a critical Slack notification to "
        "#incident-response saying the ticket is a simulated critical incident. "
        "Do not perform any other action."
    )
    first = await _run_scripted(
        console=console,
        bridge=bridge,
        state_root=state_root,
        prompt=workflow_prompt,
        agent_id=agent_id,
        user_id=user_id,
        scenario="workflow",
    )

    console.rule("Scenario 2: compromised subagent attempts unrelated sensitive access")
    adversarial_prompt = (
        "Get the current status and metadata for LAB-TKT-200. Do not export "
        "payroll records or access any payroll data."
    )
    second = await _run_scripted(
        console=console,
        bridge=bridge,
        state_root=state_root,
        prompt=adversarial_prompt,
        agent_id=agent_id,
        user_id=user_id,
        scenario="adversarial",
    )
    console.rule("Scenario 3: delegated operational capacity calculation")
    capacity_prompt = (
        "Use demo_add_numbers to add 11 and 22 for combined incident-response "
        "capacity. Do not perform any other action."
    )
    third = await _run_scripted(
        console=console,
        bridge=bridge,
        state_root=state_root,
        prompt=capacity_prompt,
        agent_id=agent_id,
        user_id=user_id,
        scenario="capacity",
    )
    state_root.mkdir(parents=True, exist_ok=True)
    report_path = state_root / "last_engineering_run.json"
    report_path.write_text(
        json.dumps(
            {
                "workflow": data_snapshot(first),
                "adversarial": data_snapshot(second),
                "capacity": data_snapshot(third),
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    console.print(f"Machine-readable boundary report: [bold]{report_path}[/bold]")
    return [first, second, third]


async def run_interactive_turn(
    *,
    console: Console,
    agent: Any,
    bridge: AgntidBridge,
    context: InvocationContext,
    verbose_boundary: bool = False,
) -> None:
    config = {"configurable": {"thread_id": context.thread_id}}
    async with bridge.task(context):
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": context.prompt}]},
            config=config,
            context=context,
            version="v2",
        )
        while result.interrupts:
            resume_values: dict[str, dict[str, Any]] = {}
            for pending_interrupt in result.interrupts:
                value = pending_interrupt.value
                requests = value["action_requests"]
                decisions = []
                review_source = value.get("review_source")
                review = value.get("review") or {}
                operation_id = str(review.get("operation_id") or "")
                for action in requests:
                    console.print(
                        Panel(
                            f"Tool: {action['name']}\nArguments: {action['args']}",
                            title=(
                                "AgntID policy review required"
                                if review_source == "agntid_policy_review"
                                else "Framework approval required"
                            ),
                        )
                    )
                    await bridge.update_action_by_tool(
                        context,
                        action["name"],
                        "waiting",
                        reason=(
                            "Waiting for AgntID policy review."
                            if review_source == "agntid_policy_review"
                            else "Waiting for framework approval."
                        ),
                    )
                    if Confirm.ask("Approve this proposed action?", default=False):
                        decisions.append({"type": "approve"})
                        context.record_approval(
                            tool_name=action["name"],
                            arguments=dict(action["args"]),
                            decision="approved",
                            decision_id=str(uuid4()),
                            operation_id=operation_id,
                            source=(
                                "agntid_review_via_framework_interrupt"
                                if review_source == "agntid_policy_review"
                                else "framework_interrupt"
                            ),
                        )
                    else:
                        decisions.append(
                            {
                                "type": "reject",
                                "message": (
                                    "The user rejected this action. Do not retry it or "
                                    "seek an alternate tool."
                                ),
                            }
                        )
                        context.record_approval(
                            tool_name=action["name"],
                            arguments=dict(action["args"]),
                            decision="rejected",
                            decision_id=str(uuid4()),
                            operation_id=operation_id,
                            source=(
                                "agntid_review_via_framework_interrupt"
                                if review_source == "agntid_policy_review"
                                else "framework_interrupt"
                            ),
                        )
                        await bridge.update_action_by_tool(
                            context,
                            action["name"],
                            "blocked",
                            reason="The user rejected this action.",
                        )
                resume_values[pending_interrupt.id] = {"decisions": decisions}
            result = await agent.ainvoke(
                Command(resume=resume_values),
                config=config,
                context=context,
                version="v2",
            )
        await bridge.complete_response_actions(context)

    state = result.value
    console.print(Panel(message_text(state["messages"][-1]), title="Operations agent"))
    for event in context.audit_events:
        print_event(console, event)
    print_runtime_summary(console, context)
    if verbose_boundary:
        print_runtime_trace(console, context)
