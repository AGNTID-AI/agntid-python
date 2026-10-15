"""
MCP tool-call wrapper: inject task context into requests and strip platform fields.
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


def _serialize_content_block(block: Any) -> Any:
    """Return an MCP content block without collapsing its native fields."""
    if isinstance(block, dict):
        return _strip_keys(block)
    model_dump = getattr(block, "model_dump", None)
    if callable(model_dump):
        return _strip_keys(model_dump(by_alias=True, exclude_none=True))
    legacy_dump = getattr(block, "dict", None)
    if callable(legacy_dump):
        return _strip_keys(legacy_dump(by_alias=True, exclude_none=True))
    return block


def _parsed_text_object(block: Any) -> dict[str, Any] | None:
    text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        import json

        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def strip_platform_fields(obj: Any) -> Any:
    """
    Extract the clean tool result from a runtime response.

    Handles:
    - fastmcp CallToolResult objects (extracts from structured_content or content)
    - Plain dicts with __agntid_result / __agntid_* keys
    - Lists and other values (traversed recursively)
    """
    content = getattr(obj, "content", None)
    if content is not None and isinstance(content, list) and not isinstance(obj, (dict, list, str)):
        sc = getattr(obj, "structured_content", None)
        if sc is None:
            sc = getattr(obj, "structuredContent", None)

        if isinstance(sc, dict):
            inner = sc.get("result", sc)
            if isinstance(inner, dict) and RESULT_KEY in inner:
                return _extract_result_dict(inner)

        for item in content:
            parsed = _parsed_text_object(item)
            if parsed is not None and RESULT_KEY in parsed:
                return _extract_result_dict(parsed)

        # Retain legacy convenience for a single plain JSON text result while
        # preserving the native MCP envelope whenever it carries multiple
        # blocks, structured content, or an intentionally empty content list.
        if len(content) == 1 and sc is None:
            parsed = _parsed_text_object(content[0])
            if parsed is not None:
                return _extract_result_dict(parsed)

        clean: dict[str, Any] = {
            "content": [_serialize_content_block(item) for item in content],
        }
        if sc is not None:
            clean["structuredContent"] = _strip_keys(sc)
        is_error = getattr(obj, "is_error", None)
        if is_error is None:
            is_error = getattr(obj, "isError", None)
        if is_error is not None:
            clean["isError"] = bool(is_error)
        return clean

    if isinstance(obj, dict):
        return _extract_result_dict(obj)
    if isinstance(obj, list):
        return [strip_platform_fields(item) for item in obj]
    return obj


T = TypeVar("T")


def wrap_client(
    client: T,
    task_id: str | None = None,
    delegation_id: str | None = None,
    *,
    task_argument: str = "agntid_task_id",
    delegation_argument: str = "agntid_delegation_id",
) -> T:
    """
    Wrap an MCP client so that every tool call includes agntid_task_id and responses
    have __agntid_* fields stripped. Returns an object that implements the same
    interface as the client (or a documented subset).

    The wrapper adds agntid_task_id to the tool arguments and strips
    any response field whose name matches __agntid_* before returning to the caller.
    Errors are propagated without stripping.

    Call set_task_id(task_id) before making tool calls so the runtime can
    correlate them to the current task. You can pass task_id here or set it later.

    :param client: The MCP client (or tool-call interface) to wrap.
    :param task_id: Optional initial task ID; default None. Set via set_task_id() if not provided.
    :param task_argument: Task-correlation argument name. Override with
        ``_task_id`` only when connecting to a legacy runtime.
    :param delegation_argument: Delegation-correlation argument name. Override
        with ``_delegation_id`` only when connecting to a legacy runtime.
    :returns: A wrapped instance; use it for all tool calls in this run.
    """
    return _WrappedClient(
        client,
        task_id,
        delegation_id,
        task_argument=task_argument,
        delegation_argument=delegation_argument,
    )


class _WrappedClient:
    """Add application-controlled task context and strip platform response fields."""

    __slots__ = (
        "_client",
        "_task_id",
        "_delegation_id",
        "_task_argument",
        "_delegation_argument",
    )

    def __init__(
        self,
        client: Any,
        task_id: str | None = None,
        delegation_id: str | None = None,
        *,
        task_argument: str = "agntid_task_id",
        delegation_argument: str = "agntid_delegation_id",
    ) -> None:
        self._client = client
        self._task_id = task_id
        self._delegation_id = delegation_id
        self._task_argument = task_argument
        self._delegation_argument = delegation_argument

    def set_task_id(self, task_id: str) -> None:
        """Update the task_id used for subsequent tool calls (e.g. for per-prompt tasks)."""
        self._task_id = task_id

    def set_delegation_id(self, delegation_id: str | None) -> None:
        """Select or clear the child delegation for subsequent tool calls."""
        self._delegation_id = delegation_id

    def _inject_context(self, arguments: dict[str, Any] | None) -> dict[str, Any]:
        args = dict(arguments) if arguments is not None else {}
        if self._task_id is not None:
            args[self._task_argument] = self._task_id
        if self._delegation_id is not None:
            args[self._delegation_argument] = self._delegation_id
        return args

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Call a tool with task context injected; strip platform fields from response."""
        args = self._inject_context(arguments)
        try:
            result = self._client.call_tool(name, args, **kwargs)
        except BaseException as e:
            return _handle_tool_error(name, e)
        if result is not None and not _is_error_result(result):
            return _wrap_result(strip_platform_fields(result), name)
        return result

    async def call_tool_async(self, name: str, arguments: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Async tool call with task context and response stripping."""
        args = self._inject_context(arguments)
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
