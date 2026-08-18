from io import StringIO

from rich.console import Console

from agntid import ExecutionPlan, PlannedAction
from agntid_deepagents_poc.data_flow import (
    print_runtime_summary,
    print_runtime_trace,
)
from agntid_deepagents_poc.identity import InvocationContext


def test_runtime_trace_accounts_for_every_context_category():
    context = InvocationContext(
        agent_id="root-agent:v1",
        user_id="alice",
        prompt="Add 11 and 22",
        task_id="task-1",
        thread_id="thread-1",
        organization_id="application-org",
        user_roles=("incident-operator",),
    )
    context.framework_events.append(
        {
            "event": "delegation_started",
            "delegation_id": "delegation-1",
        }
    )
    context.framework_events.append(
        {
            "tool": "demo_add_numbers",
            "deep_agent_name": "calculation-specialist",
            "available_to_bridge": {
                "agent_id": context.agent_id,
                "user_id": context.user_id,
                "organization_id": context.organization_id,
                "user_roles": list(context.user_roles),
                "task_id": context.task_id,
                "thread_id": context.thread_id,
                "prompt": context.prompt,
                "subagent_name": "calculation-specialist",
                "acting_agent_id": "calculation-specialist:v1",
                "delegation_id": "delegation-1",
                "delegated_intent": "Add 11 and 22 only",
                "state_keys": ["messages", "todos"],
                "message_count": 4,
                "tool_arguments": {"first_number": 11, "second_number": 22},
            },
        }
    )
    context.transport_events.extend(
        [
            {
                "phase": "task_open",
                "sent_to_agntid": {
                    "task_id": context.task_id,
                    "agent_id": context.agent_id,
                    "user_id": context.user_id,
                    "prompt": context.prompt,
                    "execution_context": {
                        "thread_id": context.thread_id,
                        "conversation": {
                            "summary": "",
                            "active_constraints": [],
                        },
                        "extensions": {
                            "agntid.deepagents_poc": {
                                "organization_id": context.organization_id,
                                "user_roles": list(context.user_roles),
                            }
                        },
                    },
                },
            },
            {
                "phase": "delegation_open",
                "sent_to_agntid": {
                    "delegation_id": "delegation-1",
                    "acting_agent_id": "calculation-specialist:v1",
                    "delegated_intent": {"text": "Add 11 and 22 only"},
                    "tool_allowlist": ["demo.add_numbers"],
                },
            },
            {
                "phase": "tool_call",
                "sent_to_agntid": {
                    "tool_name": "demo_add_numbers",
                    "arguments": {
                        "first_number": 11,
                        "second_number": 22,
                        "agntid_task_id": context.task_id,
                        "agntid_delegation_id": "delegation-1",
                    },
                },
                "received_from_agntid": {
                    "is_error": False,
                    "summary": {"status": "success"},
                },
            },
        ]
    )
    output = StringIO()
    console = Console(file=output, width=220, color_system=None)

    print_runtime_trace(console, context)

    rendered = output.getvalue()
    assert "Canonical fields observed in transport" in rendered
    assert "13 of 13 expected fields" in rendered
    assert "Bridge diagnostics not sent" in rendered
    assert "Graph state keys" in rendered
    assert "Message count" in rendered
    assert "Delegated subtask intent" in rendered
    assert "canonical delegation contract is active" in rendered
    assert rendered.count("Observed context boundary") == 1


def test_runtime_summary_is_compact_and_plan_focused():
    context = InvocationContext(
        agent_id="root-agent:v1",
        user_id="alice",
        prompt="Get LIVE-TKT-900 but do not notify anyone",
        task_id="task-compact",
    )
    context.execution_plan = ExecutionPlan(
        plan_id="plan-compact",
        actions=(
            PlannedAction(
                action_id="lookup",
                title="Investigate LIVE-TKT-900",
                expected_agent_id="incident-investigator:v1",
            ),
            PlannedAction(
                action_id="notify",
                title="Send operational notification",
                expected_agent_id="communications-specialist:v1",
                status="skipped",
                reason="Skipped by the user's explicit no-send constraint.",
            ),
        ),
    )
    context.plan_action_states["lookup"] = "completed"
    context.transport_events.extend(
        [
            {
                "phase": "delegation_open",
                "sent_to_agntid": {
                    "acting_agent_id": "incident-investigator:v1",
                },
            },
            {"phase": "tool_call", "sent_to_agntid": {"tool_name": "demo_get_ticket"}},
        ]
    )
    output = StringIO()
    console = Console(file=output, width=180, color_system=None)

    print_runtime_summary(console, context)

    rendered = output.getvalue()
    assert "AgntID run task-compact" in rendered
    assert "1 subagent" in rendered
    assert "1 tool attempt" in rendered
    assert "Investigate LIVE-TKT-900" in rendered
    assert "completed" in rendered
    assert "Send operational notification" in rendered
    assert "skipped" in rendered
    assert "Observed context boundary" not in rendered
