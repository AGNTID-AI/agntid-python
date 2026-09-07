from starlette.testclient import TestClient

import main
from agntid_agentcore.identity import AUTHORIZATION_HEADER, USER_ID_HEADER


class StubService:
    def __init__(self):
        self.context = None

    async def invoke(self, payload, context):
        self.context = context
        return {"result": payload["prompt"], "mode": "stub"}


def test_agentcore_invocations_endpoint_forwards_custom_headers(monkeypatch):
    stub = StubService()
    monkeypatch.setattr(main, "service", stub)

    with TestClient(main.app) as client:
        response = client.post(
            "/invocations",
            json={"prompt": "hello"},
            headers={
                AUTHORIZATION_HEADER: "Bearer secret-token",
                USER_ID_HEADER: "user-42",
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": "session-123",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"result": "hello", "mode": "stub"}
    assert stub.context.session_id == "session-123"
    assert stub.context.request_headers[AUTHORIZATION_HEADER.lower()] == "Bearer secret-token"
    assert stub.context.request_headers[USER_ID_HEADER.lower()] == "user-42"
