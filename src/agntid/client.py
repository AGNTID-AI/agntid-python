"""
Generic MCP client helpers (framework-agnostic).

AgntidMCPClient is the recommended MCP client for Agnt (wraps our transport; no customer fastmcp import).
Call tools on any MCP client that exposes call_tool_async or call_tool.
get_tools_list fetches the tool list from list_tools or get_tools (sync or async).
"""

from __future__ import annotations

import asyncio
from typing import Any


class AgntidMCPClient:
    """
    Agnt MCP client. Use this instead of importing a specific transport (e.g. fastmcp) in your code.
    Requires the SDK's MCP dependency (e.g. pip install agntid-sdk[msk] which includes the client transport).

    Usage:
        async with agntid.AgntidMCPClient(mcp_url) as client:
            tools = await agntid.get_tools_list(client)
            ...
    """

    def __init__(self, mcp_url: str) -> None:
        from fastmcp import Client as _FastMCPClient
        self._client = _FastMCPClient(mcp_url)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    async def __aenter__(self) -> "AgntidMCPClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.__aexit__(*args)


async def get_tools_list(client: Any) -> list[Any]:
    """
    Get the list of tools from an MCP client (list_tools or get_tools).
    Handles both sync and async methods.

    :param client: MCP client with list_tools or get_tools.
    :returns: List of tool objects/dicts.
    """
    list_fn = getattr(client, "list_tools", None) or getattr(client, "get_tools", None)
    if list_fn is None:
        return []
    if asyncio.iscoroutinefunction(list_fn):
        all_tools = await list_fn()
    else:
        all_tools = list_fn()
    return list(all_tools) if not isinstance(all_tools, list) else all_tools


async def call_tool_async(client: Any, name: str, arguments: dict[str, Any]) -> Any:
    """
    Invoke a tool on an MCP client. Works with clients that expose
    call_tool_async or call_tool (sync or returning a coroutine).

    :param client: MCP client (e.g. fastmcp Client).
    :param name: Tool name.
    :param arguments: Tool arguments dict.
    :returns: Tool result (content or structured result).
    :raises RuntimeError: If client has no call_tool or call_tool_async.
    """
    if hasattr(client, "call_tool_async"):
        return await client.call_tool_async(name, arguments)
    if hasattr(client, "call_tool"):
        raw = client.call_tool(name, arguments)
        return await raw if asyncio.iscoroutine(raw) else raw
    raise RuntimeError("MCP client has no call_tool or call_tool_async")
