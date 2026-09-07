import pytest

from agntid_agentcore.tools import langchain_tools, visible_tools


class WrappedClient:
    def __init__(self):
        self.calls = []

    async def call_tool_async(self, name, arguments):
        self.calls.append((name, arguments))
        return {"sum": arguments["first_number"] + arguments["second_number"]}


@pytest.mark.asyncio
async def test_langchain_tool_preserves_original_name_and_hides_task_argument():
    wrapped = WrappedClient()
    raw = {
        "name": "demo.add_numbers",
        "description": "Add two numbers",
        "inputSchema": {
            "type": "object",
            "properties": {
                "first_number": {"type": "integer"},
                "second_number": {"type": "integer"},
                "_task_id": {"type": "string"},
            },
            "required": ["first_number", "second_number", "_task_id"],
        },
    }

    tool = langchain_tools(wrapped, [raw])[0]

    assert tool.name == "demo_add_numbers"
    assert "_task_id" not in tool.args
    result = await tool.ainvoke({"first_number": 11, "second_number": 22})
    assert result == {"sum": 33}
    assert wrapped.calls == [
        ("demo.add_numbers", {"first_number": 11, "second_number": 22})
    ]


def test_visible_tools_intersects_runtime_list_and_operator_allowlist():
    listed = [
        {"name": "agntid_task_open"},
        {"name": "demo_add_numbers"},
        {"name": "dangerous_delete"},
    ]

    assert visible_tools(listed, frozenset({"agntid_task_open", "demo_add_numbers"})) == [
        {"name": "demo_add_numbers"}
    ]
