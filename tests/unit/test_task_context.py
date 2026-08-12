from agntid.context import DelegatedIntent, DelegationContext, ExecutionContext, FrameworkInfo
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
