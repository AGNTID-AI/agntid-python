"""
MCP tool-call wrapper: inject _task_id into requests and strip __agntid_* from responses.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

# Platform-added fields match this prefix (spec 038 Q3: A). Strip recursively.
PLATFORM_PREFIX = "__agntid_"


def strip_platform_fields(obj: Any) -> Any:
    """
    Recursively remove any key whose name starts with __agntid_ from dicts.
    Lists and other values are traversed; only dict keys are stripped.
    """
    if isinstance(obj, dict):
        return {
            k: strip_platform_fields(v)
            for k, v in obj.items()
            if not (isinstance(k, str) and k.startswith(PLATFORM_PREFIX))
        }
    if isinstance(obj, list):
        return [strip_platform_fields(item) for item in obj]
    return obj


T = TypeVar("T")


def wrap_client(client: T, task_id: str | None = None) -> T:
    """
    Wrap an MCP client so that every tool call includes _task_id and responses
    have __agntid_* fields stripped. Returns an object that implements the same
    interface as the client (or a documented subset).

    The wrapper adds _task_id to the tool arguments (037 Option B) and strips
    any response field whose name matches __agntid_* before returning to the caller.
    Errors are propagated without stripping.

    Call set_task_id(task_id) before making tool calls so the runtime can
    correlate them to the current task. You can pass task_id here or set it later.

    :param client: The MCP client (or tool-call interface) to wrap.
    :param task_id: Optional initial task ID; default None. Set via set_task_id() if not provided.
    :returns: A wrapped instance; use it for all tool calls in this run.
    """
    return _WrappedClient(client, task_id)


class _WrappedClient:
    """Wraps an MCP client to add _task_id to tool calls and strip __agntid_* from responses."""

    __slots__ = ("_client", "_task_id")

    def __init__(self, client: Any, task_id: str | None = None) -> None:
        self._client = client
        self._task_id = task_id

    def set_task_id(self, task_id: str) -> None:
        """Update the task_id used for subsequent tool calls (e.g. for per-prompt tasks)."""
        self._task_id = task_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Call a tool with _task_id injected into arguments; strip __agntid_* from response."""
        args = dict(arguments) if arguments is not None else {}
        if self._task_id is not None:
            args["_task_id"] = self._task_id
        result = self._client.call_tool(name, args, **kwargs)
        # Only strip successful response payloads; propagate errors
        if result is not None and not _is_error_result(result):
            return strip_platform_fields(result)
        return result

    # Async variant if the underlying client uses async
    async def call_tool_async(self, name: str, arguments: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Async tool call with _task_id and response stripping."""
        args = dict(arguments) if arguments is not None else {}
        if self._task_id is not None:
            args["_task_id"] = self._task_id
        client = self._client
        if hasattr(client, "call_tool_async"):
            result = await client.call_tool_async(name, args, **kwargs)
        elif hasattr(client, "call_tool"):
            raw = client.call_tool(name, args, **kwargs)
            result = await raw if asyncio.iscoroutine(raw) else raw
        else:
            raise RuntimeError("MCP client has no call_tool or call_tool_async")
        if result is not None and not _is_error_result(result):
            return strip_platform_fields(result)
        return result


def _is_error_result(result: Any) -> bool:
    """Heuristic: treat result as error if it has a top-level 'error' key (JSON-RPC style)."""
    if isinstance(result, dict):
        return "error" in result
    return False
