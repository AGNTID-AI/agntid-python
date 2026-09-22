import sys
from types import SimpleNamespace

from agntid.client import AgntidMCPClient


class FakeFastMCPClient:
    def __init__(self, url, *, auth=None):
        self.url = url
        self.auth = auth


def test_client_passes_optional_access_token_to_transport(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "fastmcp",
        SimpleNamespace(Client=FakeFastMCPClient),
    )

    client = AgntidMCPClient(
        "https://runtime.example/mcp",
        access_token="access-token",
    )

    assert client._client.url == "https://runtime.example/mcp"
    assert client._client.auth == "access-token"


def test_client_keeps_open_auth_as_default(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "fastmcp",
        SimpleNamespace(Client=FakeFastMCPClient),
    )

    client = AgntidMCPClient("http://localhost:8082/mcp")

    assert client._client.auth is None
