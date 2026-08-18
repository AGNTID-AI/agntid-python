from contextlib import asynccontextmanager
from io import StringIO
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langgraph.types import Command
from rich.console import Console

from agntid_deepagents_poc.identity import InvocationContext
from agntid_deepagents_poc.operations_demo import run_interactive_turn


class ParallelInterruptAgent:
    def __init__(self):
        self.calls = []

    async def ainvoke(self, value, **kwargs):
        self.calls.append(value)
        if len(self.calls) == 1:
            return SimpleNamespace(
                interrupts=[
                    SimpleNamespace(
                        id="interrupt-ticket",
                        value={
                            "review_source": "agntid_policy_review",
                            "action_requests": [
                                {
                                    "name": "demo_get_ticket",
                                    "args": {"ticket_id": "LIVE-TKT-900"},
                                }
                            ],
                        },
                    ),
                    SimpleNamespace(
                        id="interrupt-add",
                        value={
                            "review_source": "agntid_policy_review",
                            "action_requests": [
                                {
                                    "name": "demo_add_numbers",
                                    "args": {
                                        "first_number": 11,
                                        "second_number": 22,
                                    },
                                }
                            ],
                        },
                    ),
                ]
            )
        return SimpleNamespace(
            interrupts=[],
            value={"messages": [AIMessage(content="both stages completed")]},
        )


class RecordingBridge:
    def __init__(self):
        self.updates = []

    @asynccontextmanager
    async def task(self, context):
        yield context

    async def update_action_by_tool(self, context, tool_name, status, *, reason=""):
        self.updates.append((tool_name, status, reason))

    async def complete_response_actions(self, context):
        return None


async def test_interactive_turn_resumes_all_parallel_interrupts(monkeypatch):
    monkeypatch.setattr(
        "agntid_deepagents_poc.operations_demo.Confirm.ask",
        lambda *args, **kwargs: True,
    )
    agent = ParallelInterruptAgent()
    bridge = RecordingBridge()
    context = InvocationContext(
        agent_id="ops:v1",
        user_id="user-1",
        prompt="Get a ticket and add two values",
    )

    await run_interactive_turn(
        console=Console(file=StringIO()),
        agent=agent,
        bridge=bridge,
        context=context,
    )

    assert len(agent.calls) == 2
    resume = agent.calls[1]
    assert isinstance(resume, Command)
    assert set(resume.resume) == {"interrupt-ticket", "interrupt-add"}
    assert resume.resume["interrupt-ticket"] == {
        "decisions": [{"type": "approve"}]
    }
    assert resume.resume["interrupt-add"] == {
        "decisions": [{"type": "approve"}]
    }
    assert len(context.approval_evidence) == 2
    assert [update[:2] for update in bridge.updates] == [
        ("demo_get_ticket", "waiting"),
        ("demo_add_numbers", "waiting"),
    ]
