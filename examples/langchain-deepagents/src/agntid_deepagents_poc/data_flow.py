"""Explain the boundary between Deep Agents context and AgntID input."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .identity import InvocationContext


DATA_CONTRACT = (
    (
        "Logical agent identity",
        "InvocationContext.agent_id",
        "task_open.agent_id",
        "Actor and policy context",
    ),
    (
        "End-user identity",
        "InvocationContext.user_id",
        "task_open.user_id",
        "Actor and policy context",
    ),
    (
        "Original user prompt",
        "Messages + context.prompt",
        "task_open.prompt",
        "Intent alignment for every tool call",
    ),
    (
        "Per-prompt task",
        "context.task_id",
        "task_open + tool agntid_task_id",
        "Resolve prompt, user, and agent",
    ),
    (
        "Tool and arguments",
        "Selected tool call",
        "MCP tools/call",
        "Guardrail, policy, execution",
    ),
    (
        "Deep subagent name",
        "lc_agent_name metadata",
        "Mapped to delegation_open.acting_agent_id",
        "Child attribution and allowlist enforcement",
    ),
    (
        "Delegated subtask",
        "Deep Agents task description",
        "delegation_open.delegated_intent",
        "Independent child semantic validation",
    ),
    (
        "Conversation thread",
        "LangGraph thread_id",
        "execution_context.thread_id",
        "Cross-turn correlation",
    ),
    (
        "Conversation context",
        "Prior prompts + explicit constraints",
        "Bounded execution_context.conversation",
        "Summary and active-constraint validation",
    ),
    (
        "Organization and roles",
        "Trusted application context",
        "Namespaced execution_context extension",
        "Audit metadata only in this POC",
    ),
    (
        "Framework approval evidence",
        "Trusted HITL decision",
        "delegation_open.approval when applicable",
        "Lineage input; cryptographic verification pending",
    ),
    (
        "Memory and operational runbook",
        "Deep Agents memory files",
        "Not sent",
        "No direct visibility",
    ),
    (
        "Declared execution plan",
        "Application/framework adapter manifest",
        "execution_context.execution_plan + lifecycle updates",
        "Plan-versus-execution visibility",
    ),
    (
        "Raw conversation / reasoning",
        "Model and graph state",
        "Not sent; bounded summary only",
        "Private reasoning intentionally excluded",
    ),
)


def print_contract(console: Console) -> None:
    table = Table(title="Deep Agents -> AgntID current data contract")
    table.add_column("Data")
    table.add_column("Available in Deep Agents")
    table.add_column("Sent to AgntID")
    table.add_column("Current AgntID use")
    for row in DATA_CONTRACT:
        table.add_row(*row)
    console.print(table)


def print_runtime_summary(console: Console, context: InvocationContext) -> None:
    """Render one compact, user-facing summary for an interactive turn."""

    tool_calls = [
        event for event in context.transport_events if event.get("phase") == "tool_call"
    ]
    delegations = {
        str(event.get("sent_to_agntid", {}).get("acting_agent_id"))
        for event in context.transport_events
        if event.get("phase") == "delegation_open"
        and event.get("sent_to_agntid", {}).get("acting_agent_id")
    }
    console.print(
        f"[bold]AgntID run[/bold] {context.task_id}  "
        f"{len(delegations)} subagent{'s' if len(delegations) != 1 else ''}  "
        f"{len(tool_calls)} tool attempt{'s' if len(tool_calls) != 1 else ''}"
    )

    if context.execution_plan is None:
        return
    table = Table(show_header=True, box=None, pad_edge=False)
    table.add_column("Stage", style="bold")
    table.add_column("Owner")
    table.add_column("Status")
    table.add_column("Reason")
    for action in context.execution_plan.actions:
        status = context.plan_action_states.get(action.action_id, action.status)
        reason = action.reason
        table.add_row(
            action.title,
            action.expected_agent_id or "root response",
            status.replace("_", " "),
            reason,
        )
    console.print(table)


def print_runtime_trace(console: Console, context: InvocationContext) -> None:
    framework_tool_events = [
        event
        for event in context.framework_events
        if event.get("tool") and isinstance(event.get("available_to_bridge"), dict)
    ]
    if not framework_tool_events:
        console.print(
            Panel(
                "No AgntID MCP business tool was executed in this turn. "
                "AgntID received task_open and task_close for identity and "
                "prompt correlation, but there is no tools/call event to show. "
                "A read-only Deep Agent capability-inventory tool may still "
                "have answered the question locally.",
                title="Observed tool-call boundary",
                border_style="yellow",
            )
        )
        return

    task_open = next(
        (
            event
            for event in context.transport_events
            if event.get("phase") == "task_open"
        ),
        {},
    )
    tool_transports = [
        event for event in context.transport_events if event.get("phase") == "tool_call"
    ]
    delegation_transports = [
        event
        for event in context.transport_events
        if event.get("phase") == "delegation_open"
    ]
    used_tool_transports: set[int] = set()
    for framework in framework_tool_events:
        available = framework.get("available_to_bridge", {})
        transport: dict[str, Any] = {}
        for index, candidate in enumerate(tool_transports):
            if index in used_tool_transports:
                continue
            sent = candidate.get("sent_to_agntid", {})
            sent_arguments = sent.get("arguments", {})
            if sent.get("tool_name") != framework.get("tool"):
                continue
            expected_delegation = available.get("delegation_id")
            if expected_delegation and (
                not isinstance(sent_arguments, dict)
                or sent_arguments.get("agntid_delegation_id") != expected_delegation
            ):
                continue
            transport = candidate
            used_tool_transports.add(index)
            break
        task_sent = task_open.get("sent_to_agntid", {})
        execution_context = task_sent.get("execution_context") or {}
        conversation_context = execution_context.get("conversation") or {}
        extension = (execution_context.get("extensions") or {}).get(
            "agntid.deepagents_poc", {}
        )
        tool_sent = transport.get("sent_to_agntid", {})
        sent_arguments = tool_sent.get("arguments", {})
        delegation_id = available.get("delegation_id")
        delegation = next(
            (
                event.get("sent_to_agntid", {})
                for event in delegation_transports
                if event.get("sent_to_agntid", {}).get("delegation_id")
                == delegation_id
            ),
            {},
        )
        tool_result = transport.get("received_from_agntid", {})

        sent_checks = {
            "agent": "agent_id" in task_sent,
            "user": "user_id" in task_sent,
            "prompt": "prompt" in task_sent,
            "task": (
                "task_id" in task_sent
                and isinstance(sent_arguments, dict)
                and "agntid_task_id" in sent_arguments
            ),
            "tool": "tool_name" in tool_sent,
            "arguments": (
                "arguments" in tool_sent and isinstance(sent_arguments, dict)
            ),
            "thread": execution_context.get("thread_id")
            == available.get("thread_id"),
            "conversation": isinstance(conversation_context, dict),
        }
        if available.get("organization_id") is not None:
            sent_checks["organization"] = extension.get("organization_id") == available.get(
                "organization_id"
            )
        if available.get("user_roles"):
            sent_checks["roles"] = extension.get("user_roles") == available.get(
                "user_roles"
            )
        if delegation_id:
            sent_checks.update(
                {
                    "delegation": (
                        delegation.get("delegation_id") == delegation_id
                        and sent_arguments.get("agntid_delegation_id")
                        == delegation_id
                    ),
                    "acting_agent": delegation.get("acting_agent_id")
                    == available.get("acting_agent_id"),
                    "delegated_intent": (
                        delegation.get("delegated_intent", {}).get("text")
                        == available.get("delegated_intent")
                    ),
                }
            )

        def sent_status(check: str, route: str) -> str:
            if check not in sent_checks:
                return "NOT PRESENT IN APPLICATION CONTEXT"
            return (
                f"SENT via {route}"
                if sent_checks[check]
                else "MISSING FROM TRANSPORT"
            )

        table = Table(
            title=(
                f"Observed context boundary: {framework.get('tool')} "
                f"via {framework.get('deep_agent_name')}"
            )
        )
        table.add_column("Context component", style="bold")
        table.add_column("Deep Agents value/source")
        table.add_column("Boundary status")
        table.add_column("AgntID use today")

        def show(value: Any) -> str:
            if value is None:
                return "not present"
            if isinstance(value, (list, tuple)):
                return ", ".join(map(str, value)) or "empty"
            if isinstance(value, dict):
                return ", ".join(f"{key}={val}" for key, val in value.items())
            return str(value)

        rows = (
            (
                "Root agent ID",
                available.get("agent_id"),
                sent_status("agent", "task_open"),
                "Actor facts, policy context, audit",
            ),
            (
                "End-user ID",
                available.get("user_id"),
                sent_status("user", "task_open"),
                "Actor facts and audit (asserted unless authenticated)",
            ),
            (
                "Root prompt",
                available.get("prompt"),
                sent_status("prompt", "task_open"),
                "Intent/NLI validation and audit",
            ),
            (
                "Per-prompt task ID",
                available.get("task_id"),
                sent_status("task", "task_open + tool call"),
                "Task resolution, intent session, correlation",
            ),
            (
                "Tool name",
                framework.get("tool"),
                sent_status("tool", "tools/call"),
                "Scope gate, policy selection, audit",
            ),
            (
                "Tool arguments",
                available.get("tool_arguments"),
                sent_status("arguments", "tools/call"),
                "Schema checks, policy evaluation, execution",
            ),
            (
                "Application organization",
                available.get("organization_id"),
                sent_status("organization", "execution_context extension"),
                "Namespaced audit metadata; not an authenticated tenant claim",
            ),
            (
                "Application user roles",
                available.get("user_roles"),
                sent_status("roles", "execution_context extension"),
                "Namespaced audit metadata; not policy-authoritative",
            ),
            (
                "Conversation thread ID",
                available.get("thread_id"),
                sent_status("thread", "execution_context"),
                "Cross-turn correlation",
            ),
            (
                "Bounded conversation context",
                conversation_context,
                sent_status("conversation", "execution_context"),
                "Prior-request summary and active constraints",
            ),
            (
                "Calling subagent",
                (
                    f"{available.get('subagent_name')} -> "
                    f"{available.get('acting_agent_id')}"
                ),
                (
                    sent_status("acting_agent", "delegation_open")
                    if delegation_id
                    else "ROOT CALL; NO CHILD DELEGATION"
                ),
                "Trusted adapter mapping gives child attribution",
            ),
            (
                "Delegation ID",
                delegation_id,
                (
                    sent_status("delegation", "delegation_open + tool call")
                    if delegation_id
                    else "NOT APPLICABLE"
                ),
                "Parent/child lineage and call correlation",
            ),
            (
                "Delegated subtask intent",
                available.get("delegated_intent"),
                (
                    sent_status("delegated_intent", "delegation_open")
                    if delegation_id
                    else "NOT APPLICABLE"
                ),
                "Independent delegated semantic validation",
            ),
            (
                "Approval evidence",
                delegation.get("approval"),
                (
                    "SENT via delegation_open"
                    if delegation.get("approval")
                    else "NOT APPLICABLE FOR THIS CALL"
                ),
                "Recorded lineage; independent verification remains pending",
            ),
            (
                "AgntID tool outcome",
                tool_result.get("summary", {}).get("status"),
                (
                    "RECEIVED success"
                    if tool_result.get("is_error") is False
                    else "RECEIVED error/denial"
                ),
                "Authoritative execution or denial evidence",
            ),
            (
                "Graph state keys",
                available.get("state_keys"),
                "BRIDGE DIAGNOSTIC; NOT SENT",
                "No framework-state observability",
            ),
            (
                "Message count",
                available.get("message_count"),
                "BRIDGE DIAGNOSTIC; NOT SENT",
                "No loop/turn-volume signal",
            ),
            (
                "Conversation history",
                "graph messages and prior prompts",
                "BOUNDED SUMMARY SENT; RAW TRANSCRIPT NOT SENT",
                "Accumulated context without transmitting full history",
            ),
            (
                "Memory/runbook evidence",
                "Deep Agents backend files",
                "NOT CAPTURED OR SENT",
                "No memory provenance or poisoning evidence",
            ),
            (
                "Declared plan evidence",
                (
                    context.execution_plan.to_dict()
                    if context.execution_plan is not None
                    else None
                ),
                (
                    "SENT via task_open + action lifecycle updates"
                    if context.execution_plan is not None
                    else "NOT DECLARED BY THIS ADAPTER"
                ),
                "Plan-versus-observed-execution governance",
            ),
            (
                "Raw model reasoning",
                "private model state",
                "INTENTIONALLY NOT SENT",
                "Use structured rationale; do not transmit chain-of-thought",
            ),
        )
        for component, value, status, use in rows:
            table.add_row(component, show(value), status, use)

        console.print(table)
        summary = Table(show_header=False, box=None, title="Boundary accounting")
        summary.add_row(
            "Canonical fields observed in transport",
            f"{sum(sent_checks.values())} of {len(sent_checks)} expected fields",
        )
        summary.add_row("Bridge diagnostics not sent", "2 components")
        summary.add_row("Application artifacts not sent", "2 components")
        summary.add_row("Raw conversation replaced by bounded context", "1 category")
        summary.add_row("Intentionally withheld", "1 component (raw reasoning)")
        console.print(summary)
        console.print(
            Panel(
                "The canonical delegation contract is active: trusted child "
                "identity, delegated intent, tool allowlist, and lineage are "
                "sent. Matching HITL evidence is sent when present. The local "
                "open transport still does not cryptographically authenticate "
                "caller identity or approval evidence.",
                title="Multi-agent contract status",
                border_style="green",
            )
        )


def data_snapshot(context: InvocationContext) -> dict[str, Any]:
    """Machine-readable telemetry for tests or later visualization."""

    return {
        "identity": {
            "agent_id": context.agent_id,
            "user_id": context.user_id,
            "organization_id": context.organization_id,
            "user_roles": list(context.user_roles),
            "task_id": context.task_id,
            "thread_id": context.thread_id,
        },
        "framework_events": context.framework_events,
        "transport_events": context.transport_events,
        "agntid_events": context.audit_events,
    }
