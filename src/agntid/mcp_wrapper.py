"""
MCP tool-call wrapper: inject _task_id into requests and strip __agntid_* from responses.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

from agntid.denial import is_denial_error, parse_denial_from_exception, set_last_denial
from agntid.display import DenialResult, ToolResult, ToolResultScalar

# Platform-added fields match this prefix (spec 038 Q3: A). Strip recursively.
PLATFORM_PREFIX = "__agntid_"
# The runtime wraps the real tool result under this key.
RESULT_KEY = "__agntid_result"


def _strip_keys(obj: Any) -> Any:
    """Recursively remove any key starting with __agntid_ from nested dicts/lists."""
    if isinstance(obj, dict):
        return {
            k: _strip_keys(v)
            for k, v in obj.items()
            if not (isinstance(k, str) and k.startswith(PLATFORM_PREFIX))
        }
    if isinstance(obj, list):
        return [_strip_keys(item) for item in obj]
    return obj


def _extract_result_dict(d: dict[str, Any]) -> Any:
    """
    If d contains __agntid_result, return its value (the clean tool output).
    Otherwise strip all __agntid_* keys and return what remains.
    """
    if RESULT_KEY in d:
        return _strip_keys(d[RESULT_KEY])
    return _strip_keys(d)


def strip_platform_fields(obj: Any) -> Any:
    """
    Extract the clean tool result from a runtime response.

    Handles:
    - fastmcp CallToolResult objects (extracts from structured_content or content)
    - Plain dicts with __agntid_result / __agntid_* keys
    - Lists and other values (traversed recursively)
    """
    sc = getattr(obj, "structured_content", None)
    if sc is not None and isinstance(sc, dict):
        inner = sc.get("result", sc)
        if isinstance(inner, dict):
            return _extract_result_dict(inner)
        return _strip_keys(sc)

    content = getattr(obj, "content", None)
    if content is not None and isinstance(content, list) and not isinstance(obj, (dict, list, str)):
        for item in content:
            text = getattr(item, "text", None)
            if text and isinstance(text, str):
                try:
                    import json
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        return _extract_result_dict(parsed)
                except (ValueError, TypeError):
                    pass
        return obj

    if isinstance(obj, dict):
        return _extract_result_dict(obj)
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
        try:
            result = self._client.call_tool(name, args, **kwargs)
        except BaseException as e:
            return _handle_tool_error(name, e)
        if result is not None and not _is_error_result(result):
            return _wrap_result(strip_platform_fields(result), name)
        return result

    async def call_tool_async(self, name: str, arguments: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Async tool call with _task_id and response stripping."""
        args = dict(arguments) if arguments is not None else {}
        if self._task_id is not None:
            args["_task_id"] = self._task_id
        try:
            client = self._client
            if hasattr(client, "call_tool_async"):
                result = await client.call_tool_async(name, args, **kwargs)
            elif hasattr(client, "call_tool"):
                raw = client.call_tool(name, args, **kwargs)
                result = await raw if asyncio.iscoroutine(raw) else raw
            else:
                raise RuntimeError("MCP client has no call_tool or call_tool_async")
        except BaseException as e:
            return _handle_tool_error(name, e)
        if result is not None and not _is_error_result(result):
            return _wrap_result(strip_platform_fields(result), name)
        return result


def _wrap_result(clean: Any, tool_name: str) -> Any:
    """Wrap a cleaned result in a ToolResult (dict) or ToolResultScalar so print() renders rich."""
    if isinstance(clean, dict):
        return ToolResult(clean, tool_name=tool_name)
    return ToolResultScalar(clean, tool_name=tool_name)


def _handle_tool_error(tool_name: str, exc: BaseException) -> DenialResult:
    """
    Catch policy denials from the runtime and store them via set_last_denial
    so callers can use get_last_denial() instead of parsing raw exceptions.
    Non-denial errors are re-raised.
    """
    if not is_denial_error(exc):
        raise exc
    user_msg, denial_info = parse_denial_from_exception(exc)
    if denial_info:
        set_last_denial(tool_name, denial_info)
    else:
        set_last_denial(tool_name, {"reason": str(exc), "policy_name": ""})
    return DenialResult(user_msg, tool_name=tool_name)


def _is_error_result(result: Any) -> bool:
    """Heuristic: treat result as error if it has a top-level 'error' key (JSON-RPC style)."""
    if isinstance(result, dict):
        return "error" in result
    return False
