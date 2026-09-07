"""Per-invocation AgentCore, LangGraph, MCP, and AgntID lifecycle."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import agntid
from fastmcp import Client as FastMCPClient
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from .config import Settings
from .errors import InvocationError
from .identity import bearer_token, require_user_id
from .model import load_model
from .tools import langchain_tools, original_name, visible_tools

SYSTEM_PROMPT = """You are an operations assistant. Use only the supplied tools.
Do not invent tool results. If AgntID denies a call, explain the denial and stop.
"""

AgentRunner = Callable[[str, list[Any], str | None, Settings], Awaitable[Any]]
ClientFactory = Callable[[str, str | None], Any]


def _default_client_factory(url: str, token: str | None):
    return FastMCPClient(url, auth=token)


async def _default_agent_runner(
    prompt: str,
    tools: list[Any],
    session_id: str | None,
    settings: Settings,
) -> Any:
    graph = create_react_agent(
        load_model(settings),
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )
    config = None
    if session_id:
        config = {"configurable": {"thread_id": session_id}}
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=config,
    )
    return result["messages"][-1].content


def _plain_result(value: Any) -> Any:
    if hasattr(value, "value"):
        value = value.value
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


def _payload_prompt(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        raise InvocationError(400, "The invocation payload must be a JSON object.")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise InvocationError(400, "The invocation payload requires a non-empty prompt.")
    if len(prompt) > 100_000:
        raise InvocationError(400, "The prompt is too large.")
    return prompt.strip()


def _direct_request(payload: Mapping[str, Any]) -> tuple[str, dict[str, Any]] | None:
    direct = payload.get("direct_tool")
    if direct is None:
        return None
    if not isinstance(direct, Mapping):
        raise InvocationError(400, "direct_tool must be a JSON object.")
    name = direct.get("name")
    arguments = direct.get("arguments", {})
    if not isinstance(name, str) or not name.strip() or not isinstance(arguments, dict):
        raise InvocationError(400, "direct_tool requires a name and object arguments.")
    return name.strip(), dict(arguments)


@dataclass
class AgentCoreService:
    settings: Settings
    client_factory: ClientFactory = _default_client_factory
    agent_runner: AgentRunner = _default_agent_runner

    @classmethod
    def from_env(cls) -> "AgentCoreService":
        return cls(Settings.from_env())

    async def invoke(self, payload: Any, context: Any) -> dict[str, Any]:
        prompt = _payload_prompt(payload)
        headers = getattr(context, "request_headers", None)
        user_id = require_user_id(headers)
        token = bearer_token(headers, required=self.settings.require_bearer)
        session_id = getattr(context, "session_id", None)
        direct = _direct_request(payload)
        if direct and not self.settings.enable_direct_smoke:
            raise InvocationError(403, "Direct tool smoke mode is disabled.")
        if direct and direct[0] not in self.settings.tool_allowlist:
            raise InvocationError(403, "The requested direct tool is not allowlisted.")

        client = self.client_factory(self.settings.mcp_url, token)
        async with client:
            listed = await agntid.get_tools_list(client)
            allowed = visible_tools(listed, self.settings.tool_allowlist)
            if not allowed:
                raise InvocationError(403, "No allowlisted AgntID tools are visible to this user.")

            task_id = agntid.create_task(self.settings.agent_id, user_id, prompt)
            wrapped = agntid.wrap_client(client, task_id)
            async with agntid.task_context(client, task_id):
                ok, message = await agntid.send_task_open_checked(
                    client,
                    task_id,
                    self.settings.agent_id,
                    user_id,
                    prompt,
                )
                if not ok:
                    raise InvocationError(403, message or "AgntID rejected the task.")

                if direct:
                    name, arguments = direct
                    if name not in {original_name(tool) for tool in allowed}:
                        raise InvocationError(403, "The requested tool is not visible to this user.")
                    output = await wrapped.call_tool_async(name, arguments)
                    mode = "direct-smoke"
                else:
                    tools = langchain_tools(wrapped, allowed)
                    output = await self.agent_runner(
                        prompt,
                        tools,
                        session_id,
                        self.settings,
                    )
                    mode = "langgraph"

                denial = agntid.get_last_denial(clear=True)
                response = {
                    "result": _plain_result(output),
                    "task_id": task_id,
                    "mode": mode,
                    "denied": bool(denial),
                    "visible_tool_count": len(allowed),
                }
                if session_id:
                    response["session_id"] = session_id
                if denial:
                    response["denial"] = agntid.format_denial(denial)
                return response
