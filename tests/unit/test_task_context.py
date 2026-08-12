from agntid.context import (
    DelegatedIntent,
    DelegationContext,
    ExecutionContext,
    ExecutionPlan,
    FrameworkInfo,
    PlannedAction,
)
from agntid.task import delegation_open_arguments, task_open_arguments


def test_task_open_arguments_accept_canonical_object():
    context = ExecutionContext(
        framework=FrameworkInfo("test", "1.0.0"),
        turn_id="task-1",
        root_task_id="task-1",
        root_agent_id="root",
    )

    payload = task_open_arguments(
        "task-1",
        "root",
        "user-1",
        "Get status",
        execution_context=context,
    )

    assert payload["execution_context"]["root_agent_id"] == "root"


def test_task_open_arguments_carries_framework_neutral_execution_plan():
    context = ExecutionContext(
        framework=FrameworkInfo("test", "1.0.0", ("execution_plan",)),
        turn_id="task-1",
        root_task_id="task-1",
        root_agent_id="root",
        execution_plan=ExecutionPlan(
            plan_id="plan-1",
            actions=(
                PlannedAction(
                    action_id="lookup",
                    title="Lookup ticket",
                    tool_name="tickets.get",
                    expected_agent_id="researcher:v1",
                ),
            ),
        ),
    )

    payload = task_open_arguments(
        "task-1", "root", "user-1", "Get status", execution_context=context
    )

    plan = payload["execution_context"]["execution_plan"]
    assert plan["plan_id"] == "plan-1"
    assert plan["actions"][0]["tool_name"] == "tickets.get"


def test_task_open_arguments_carries_conditional_action_contract():
    context = ExecutionContext(
        framework=FrameworkInfo("test", "1.0.0", ("execution_plan",)),
        turn_id="task-1",
        root_task_id="task-1",
        root_agent_id="root",
        execution_plan=ExecutionPlan(
            plan_id="plan-1",
            actions=(
                PlannedAction(
                    action_id="notify",
                    title="Notify if active",
                    requirement="conditional",
                    condition="The verified ticket is active.",
                    condition_status="pending",
                ),
            ),
        ),
    )

    payload = task_open_arguments(
        "task-1", "root", "user-1", "Notify if active", execution_context=context
    )

    action = payload["execution_context"]["execution_plan"]["actions"][0]
    assert action["requirement"] == "conditional"
    assert action["condition_status"] == "pending"


def test_delegation_open_arguments_adds_root_task_id():
    delegation = DelegationContext(
        delegation_id="d1",
        parent_agent_id="root",
        acting_agent_id="researcher",
        delegated_intent=DelegatedIntent("Read LIVE-42"),
    )

    payload = delegation_open_arguments("task-1", delegation)

    assert payload["task_id"] == "task-1"
    assert payload["acting_agent_id"] == "researcher"
