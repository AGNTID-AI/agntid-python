from types import SimpleNamespace

import pytest

from agntid_agentcore.config import Settings
from agntid_agentcore.errors import InvocationError
from agntid_agentcore.identity import AUTHORIZATION_HEADER, USER_ID_HEADER
from agntid_agentcore.service import AgentCoreService


class FakeMCPClient:
    def __init__(self):
        self.events = []

    async def __aenter__(self):
        self.events.append(("connect",))
        return self

    async def __aexit__(self, *args):
        self.events.append(("disconnect",))

    async def list_tools(self):
        return [
            {
                "name": "agntid_task_open",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "agntid_task_close",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "demo_add_numbers",
                "description": "Add two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "first_number": {"type": "integer"},
                        "second_number": {"type": "integer"},
                        "_task_id": {"type": "string"},
                    },
                    "required": ["first_number", "second_number"],
                },
            },
            {"name": "not_allowlisted"},
        ]

    async def call_tool(self, name, arguments):
        self.events.append(("call", name, dict(arguments)))
        if name == "agntid_task_open":
            return {"ok": True}
        if name == "agntid_task_close":
            return {"ok": True}
        if name == "demo_add_numbers":
            return {
                "__agntid_result": {
                    "sum": arguments["first_number"] + arguments["second_number"]
                },
                "__agntid_trace_id": "must-not-reach-model",
            }
        raise AssertionError(name)


def settings(*, direct=False, require_bearer=True):
    return Settings(
        mcp_url="https://runtime.example/mcp",
        agent_id="aws-agentcore-langchain:v1",
        tool_allowlist=frozenset({"demo_add_numbers"}),
        enable_direct_smoke=direct,
        require_bearer=require_bearer,
    )


def context():
    return SimpleNamespace(
        session_id="session-123",
        request_headers={
            AUTHORIZATION_HEADER: "Bearer user-access-token",
            USER_ID_HEADER: "user-42",
        },
    )


@pytest.mark.asyncio
async def test_langgraph_path_opens_calls_and_closes_one_correlated_task():
    client = FakeMCPClient()
    captured = {}

    async def runner(prompt, tools, session_id, _settings):
        captured["prompt"] = prompt
        captured["tool_names"] = [tool.name for tool in tools]
        captured["session_id"] = session_id
        return await tools[0].ainvoke({"first_number": 11, "second_number": 22})

    received_auth = []

    def client_factory(url, token):
        received_auth.append((url, token))
        return client

    service = AgentCoreService(settings(), client_factory, runner)
    response = await service.invoke({"prompt": "Add 11 and 22"}, context())

    assert received_auth == [("https://runtime.example/mcp", "user-access-token")]
    assert captured == {
        "prompt": "Add 11 and 22",
        "tool_names": ["demo_add_numbers"],
        "session_id": "session-123",
    }
    assert response["result"] == {"sum": 33}
    assert response["mode"] == "langgraph"
    assert response["denied"] is False

    calls = [event for event in client.events if event[0] == "call"]
    assert [event[1] for event in calls] == [
        "agntid_task_open",
        "demo_add_numbers",
        "agntid_task_close",
    ]
    assert calls[0][2]["user_id"] == "user-42"
    assert calls[1][2]["_task_id"] == response["task_id"]
    assert "__agntid_trace_id" not in response["result"]


@pytest.mark.asyncio
async def test_direct_smoke_exercises_task_and_tool_without_model_or_aws():
    client = FakeMCPClient()

    async def model_must_not_run(*args):
        raise AssertionError("model path ran")

    service = AgentCoreService(
        settings(direct=True),
        lambda _url, _token: client,
        model_must_not_run,
    )
    response = await service.invoke(
        {
            "prompt": "Local deterministic smoke",
            "direct_tool": {
                "name": "demo_add_numbers",
                "arguments": {"first_number": 11, "second_number": 22},
            },
        },
        context(),
    )

    assert response["result"] == {"sum": 33}
    assert response["mode"] == "direct-smoke"


@pytest.mark.asyncio
async def test_missing_identity_fails_before_mcp_connection():
    def client_must_not_be_created(*args):
        raise AssertionError("MCP client was created")

    service = AgentCoreService(settings(), client_must_not_be_created)
    with pytest.raises(InvocationError) as caught:
        await service.invoke(
            {"prompt": "hello"},
            SimpleNamespace(session_id=None, request_headers={}),
        )

    assert caught.value.status_code == 401


@pytest.mark.asyncio
async def test_direct_smoke_is_disabled_by_default():
    service = AgentCoreService(settings(), lambda _url, _token: FakeMCPClient())
    with pytest.raises(InvocationError) as caught:
        await service.invoke(
            {
                "prompt": "try direct",
                "direct_tool": {"name": "demo_add_numbers", "arguments": {}},
            },
            context(),
        )

    assert caught.value.status_code == 403
