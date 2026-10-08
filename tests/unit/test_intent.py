from types import SimpleNamespace

import pytest

from agntid.intent import (
    IntentPreparationError,
    filter_tools_for_task,
    parse_task_open_details,
)


def task_open_payload(relevant_tool_ids, relevant_tool_names=None):
    return {
        "ok": True,
        "reason": None,
        "intent": {
            "prepared": True,
            "eligible_tool_count": 3,
            "relevant_tool_count": len(relevant_tool_ids),
            "no_relevant_tools": not relevant_tool_ids,
            "snapshot": {
                "id": "snapshot-1",
                "engine_id": "contextual",
                "engine_version": "v1",
                "task_id": "task-1",
                "tasks": [{"id": "t1", "instruction": "Add 11 and 22"}],
                "constraints": ["Do not send notifications"],
                "relevant_tool_ids": relevant_tool_ids,
                "relevant_tool_names": (
                    relevant_tool_ids
                    if relevant_tool_names is None
                    else relevant_tool_names
                ),
            },
        },
    }


def test_parse_task_open_details_preserves_intent_snapshot():
    parsed = parse_task_open_details(task_open_payload(["demo_add_numbers"]))

    assert parsed.ok is True
    assert parsed.intent_prepared is True
    assert parsed.eligible_tool_count == 3
    assert parsed.relevant_tool_count == 1
    assert parsed.snapshot is not None
    assert parsed.snapshot.engine_id == "contextual"
    assert parsed.snapshot.relevant_tool_ids == ("demo_add_numbers",)
    assert parsed.snapshot.relevant_tool_names == ("demo_add_numbers",)
    assert parsed.snapshot.constraints == ("Do not send notifications",)


def test_parse_task_open_details_unwraps_structured_result():
    result = SimpleNamespace(
        structured_content={"result": task_open_payload(["demo_add_numbers"])}
    )

    assert parse_task_open_details(result).snapshot.snapshot_id == "snapshot-1"


def test_filter_tools_for_task_only_returns_runtime_shortlist():
    tools = [
        SimpleNamespace(name="agntid_task_open"),
        SimpleNamespace(name="demo_add_numbers"),
        SimpleNamespace(name="demo_send_notification"),
    ]
    parsed = parse_task_open_details(task_open_payload(["demo_add_numbers"]))

    assert [tool.name for tool in filter_tools_for_task(tools, parsed)] == [
        "demo_add_numbers"
    ]


def test_filter_tools_for_task_uses_public_names_for_canonical_action_ids():
    tools = [SimpleNamespace(name="tickets_delete")]
    parsed = parse_task_open_details(
        task_open_payload(["tickets.delete"], ["tickets_delete"])
    )

    assert filter_tools_for_task(tools, parsed) == tools


def test_filter_tools_for_task_preserves_valid_empty_shortlist():
    tools = [SimpleNamespace(name="demo_add_numbers")]
    parsed = parse_task_open_details(task_open_payload([]))

    assert filter_tools_for_task(tools, parsed) == []


def test_filter_tools_for_task_fails_closed_without_preparation():
    parsed = parse_task_open_details(
        {
            "ok": True,
            "intent": {"prepared": False, "reason": "intent_engine_error"},
        }
    )

    with pytest.raises(IntentPreparationError, match="intent_engine_error"):
        filter_tools_for_task([{"name": "demo_add_numbers"}], parsed)
