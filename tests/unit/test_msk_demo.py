import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import semantic_kernel


DEMO_PATH = Path(__file__).parents[2] / "examples" / "msk" / "msk_demo.py"
SPEC = importlib.util.spec_from_file_location("agntid_msk_demo", DEMO_PATH)
assert SPEC and SPEC.loader
msk_demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(msk_demo)


class FakeClient:
    def __init__(self, url, *, access_token=None):
        self.url = url
        self.access_token = access_token

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_runtime_check_builds_plugin_without_model(monkeypatch, capsys):
    monkeypatch.setenv("AGNTID_ACCESS_TOKEN", "access-token")
    monkeypatch.setattr(
        msk_demo.agntid,
        "require_env",
        lambda *args, **kwargs: {"AGNTID_MCP_URL": "https://runtime.test/mcp"},
    )
    monkeypatch.setattr(msk_demo.agntid, "AgntidMCPClient", FakeClient)

    async def fake_tools(client):
        assert client.access_token == "access-token"
        return [SimpleNamespace(name="demo_add_numbers")]

    monkeypatch.setattr(msk_demo.agntid, "get_tools_list", fake_tools)
    monkeypatch.setattr(msk_demo.agntid, "wrap_client", lambda client: object())
    monkeypatch.setattr(
        msk_demo.agntid.msk,
        "create_plugin_from_mcp_tools",
        lambda *args, **kwargs: "plugin",
    )

    class FakeKernel:
        def add_plugin(self, plugin, *, plugin_name):
            assert plugin == "plugin"
            assert plugin_name == "MCPTools"

    monkeypatch.setattr(semantic_kernel, "Kernel", FakeKernel)

    await msk_demo._check_runtime()

    assert "MSK readiness passed" in capsys.readouterr().out
