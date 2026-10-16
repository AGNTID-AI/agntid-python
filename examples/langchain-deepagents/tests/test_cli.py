from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console

import agntid_deepagents_poc.cli as cli
from agntid_deepagents_poc.cli import _exception_summary


def test_exception_summary_expands_nested_task_group_errors():
    error = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [RuntimeError("provider connection reset")],
    )

    rendered = _exception_summary(error)

    assert "ExceptionGroup: unhandled errors in a TaskGroup" in rendered
    assert "RuntimeError: provider connection reset" in rendered


class _ConnectedBridge:
    def connect(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


def _smoke_args(framework):
    return SimpleNamespace(
        framework=framework,
        first=11,
        second=22,
        agent_id="smoke-agent",
        user_id="smoke-user",
    )


@pytest.mark.parametrize("framework", ["langchain", "deepagents"])
@pytest.mark.asyncio
async def test_framework_smoke_prints_success_when_call_is_not_denied(
    monkeypatch, framework
):
    async def fake_run_framework_agent(**kwargs):
        assert kwargs["framework"] == framework
        return (
            "The protected arithmetic tool call completed.",
            [],
        )

    monkeypatch.setattr(cli, "_bridge", lambda _args: _ConnectedBridge())
    monkeypatch.setattr(cli, "run_framework_agent", fake_run_framework_agent)
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=120)

    await cli._framework_smoke(_smoke_args(framework), console)

    rendered = output.getvalue()
    assert "The protected arithmetic tool call completed." in rendered


@pytest.mark.parametrize("framework", ["langchain", "deepagents"])
@pytest.mark.asyncio
async def test_framework_smoke_denial_preserves_diagnostics_and_fails(
    monkeypatch, framework
):
    async def fake_run_framework_agent(**kwargs):
        assert kwargs["framework"] == framework
        return (
            "The protected arithmetic tool call completed.",
            [
                {
                    "status": "denied",
                    "policy_allowed": False,
                    "denial_reason": "Policy denied the request.",
                    "correlation_id": "corr-denied-456",
                }
            ],
        )

    monkeypatch.setattr(cli, "_bridge", lambda _args: _ConnectedBridge())
    monkeypatch.setattr(cli, "run_framework_agent", fake_run_framework_agent)
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=120)

    with pytest.raises(cli.FrameworkSmokeFailed, match="corr-denied-456"):
        await cli._framework_smoke(_smoke_args(framework), console)

    rendered = output.getvalue()
    assert "AgntID execution denied" in rendered
    assert "Policy denied the request." in rendered
    assert "corr-denied-456" in rendered
    assert "The protected arithmetic tool call completed." not in rendered
