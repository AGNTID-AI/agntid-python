from __future__ import annotations

import pytest

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
