from __future__ import annotations

from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult

from agntid import wrap_client


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"value": "ok"}


class AsyncRecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def call_tool_async(
        self, name: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append((name, arguments))
        return {"value": "ok"}


def test_wrap_client_injects_canonical_context_without_mutating_input() -> None:
    client = RecordingClient()
    arguments: dict[str, object] = {
        "value": 1,
        "agntid_task_id": "model-supplied-task",
        "agntid_delegation_id": "model-supplied-delegation",
    }
    wrapped = wrap_client(client, task_id="task-123", delegation_id="delegation-456")

    result = wrapped.call_tool("example", arguments)

    assert result == {"value": "ok"}
    assert client.calls == [
        (
            "example",
            {
                "value": 1,
                "agntid_task_id": "task-123",
                "agntid_delegation_id": "delegation-456",
            },
        )
    ]
    assert arguments == {
        "value": 1,
        "agntid_task_id": "model-supplied-task",
        "agntid_delegation_id": "model-supplied-delegation",
    }


@pytest.mark.asyncio
async def test_wrap_client_injects_canonical_context_for_async_calls() -> None:
    client = AsyncRecordingClient()
    wrapped = wrap_client(client, task_id="task-123", delegation_id="delegation-456")

    await wrapped.call_tool_async("example", {"value": 1})

    assert client.calls == [
        (
            "example",
            {
                "value": 1,
                "agntid_task_id": "task-123",
                "agntid_delegation_id": "delegation-456",
            },
        )
    ]


def test_wrap_client_supports_explicit_legacy_argument_names() -> None:
    client = RecordingClient()
    wrapped = wrap_client(
        client,
        task_id="task-123",
        delegation_id="delegation-456",
        task_argument="_task_id",
        delegation_argument="_delegation_id",
    )

    wrapped.call_tool("example", {})

    assert client.calls == [
        (
            "example",
            {"_task_id": "task-123", "_delegation_id": "delegation-456"},
        )
    ]


class NativeResultClient:
    def __init__(self, result: object) -> None:
        self.result = result

    def call_tool(self, _name: str, _arguments: dict[str, object]) -> object:
        return self.result


def test_wrap_client_preserves_ordered_content_and_structured_content() -> None:
    native_result = CallToolResult.model_validate({
        "content": [
            {"type": "text", "text": "first"},
            {"type": "image", "data": "Zm9v", "mimeType": "image/png"},
            {"type": "resource", "resource": {
                "uri": "file:///item.txt", "mimeType": "text/plain", "text": "last",
            }},
        ],
        "structuredContent": {"count": 3},
        "isError": False,
    })

    result = wrap_client(NativeResultClient(native_result)).call_tool("example", {})

    assert [block["type"] for block in result["content"]] == [
        "text", "image", "resource",
    ]
    assert result["structuredContent"] == {"count": 3}
    assert result["isError"] is False


def test_wrap_client_preserves_empty_content_with_structured_content() -> None:
    native_result = CallToolResult(
        content=[], structuredContent={"count": 0}, isError=False
    )

    result = wrap_client(NativeResultClient(native_result)).call_tool("example", {})

    assert result == {
        "content": [],
        "structuredContent": {"count": 0},
        "isError": False,
    }


def test_wrap_client_keeps_legacy_single_json_text_convenience() -> None:
    native_result = SimpleNamespace(
        content=[SimpleNamespace(text='{"value": "ok"}')],
        structured_content=None,
        is_error=False,
    )

    result = wrap_client(NativeResultClient(native_result)).call_tool("example", {})

    assert result == {"value": "ok"}
