"""Framework-specific runners sharing the same AgntID bridge."""

from __future__ import annotations

from typing import Any, Literal

from deepagents import create_deep_agent
from langchain.agents import create_agent
from langchain_core.messages import BaseMessage

from .bridge import AgntidBridge
from .identity import InvocationContext

DEMO_ALLOWLIST = {"demo_add_numbers"}

SYSTEM_PROMPT = """\
You are a narrowly scoped arithmetic agent. Use demo_add_numbers whenever the
user asks you to add values. Never invent a successful result when a tool call
is denied. Explain an AgntID policy denial clearly and do not bypass or retry it
with changed arguments unless the user explicitly supplies different values.
"""


def build_agent(
    framework: Literal["langchain", "deepagents"],
    model: Any,
    bridge: AgntidBridge,
):
    """Build either harness over the identical AgntID-protected tool set."""

    tools = bridge.agent_tools(DEMO_ALLOWLIST)
    factory = create_agent if framework == "langchain" else create_deep_agent
    return factory(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        context_schema=InvocationContext,
        name=f"agntid-{framework}-demo",
    )


async def run_framework_agent(
    *,
    framework: Literal["langchain", "deepagents"],
    model: Any,
    bridge: AgntidBridge,
    context: InvocationContext,
) -> tuple[str, list[dict[str, Any]]]:
    """Run one prompt through the chosen framework and AgntID task boundary."""

    agent = build_agent(framework, model, bridge)
    async with bridge.task(context):
        state = await agent.ainvoke(
            {"messages": [{"role": "user", "content": context.prompt}]},
            context=context,
        )

    messages: list[BaseMessage] = state["messages"]
    final = messages[-1].content
    if not isinstance(final, str):
        final = str(final)
    return final, context.audit_events
