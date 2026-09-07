"""Convert AgntID MCP tool schemas to trusted LangChain tools."""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from langchain_core.tools import StructuredTool

from agntid.task import (
    ACTION_UPDATE_TOOL,
    DELEGATION_CLOSE_TOOL,
    DELEGATION_OPEN_TOOL,
    TASK_CLOSE_TOOL,
    TASK_OPEN_TOOL,
)

CONTROL_TOOLS = frozenset(
    {
        TASK_OPEN_TOOL,
        TASK_CLOSE_TOOL,
        ACTION_UPDATE_TOOL,
        DELEGATION_OPEN_TOOL,
        DELEGATION_CLOSE_TOOL,
    }
)
_UNSAFE_NAME = re.compile(r"[^0-9A-Za-z_-]")


def _field(tool: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(tool, dict) and name in tool:
            return tool[name]
        value = getattr(tool, name, None)
        if value is not None:
            return value
    return default


def original_name(tool: Any) -> str:
    return str(_field(tool, "name", default=""))


def visible_tools(tools: Iterable[Any], allowlist: frozenset[str]) -> list[Any]:
    """Intersect the runtime-filtered list with the operator's smaller allowlist."""

    return [
        tool
        for tool in tools
        if original_name(tool) in allowlist and original_name(tool) not in CONTROL_TOOLS
    ]


def _model_name(name: str) -> str:
    safe = _UNSAFE_NAME.sub("_", name)
    if not safe or not (safe[0].isalpha() or safe[0] == "_"):
        safe = f"tool_{safe}"
    return safe


def langchain_tools(wrapped_client: Any, tools: Iterable[Any]) -> list[StructuredTool]:
    """Create model-visible tools whose calls always use the wrapped client."""

    converted: list[StructuredTool] = []
    used_names: set[str] = set()
    for tool in tools:
        mcp_name = original_name(tool)
        name = _model_name(mcp_name)
        if name in used_names:
            raise RuntimeError(f"MCP tool name collision after sanitizing: {mcp_name}")
        used_names.add(name)
        description = str(_field(tool, "description", default="") or mcp_name)
        schema = _field(tool, "inputSchema", "input_schema", default={}) or {}
        if not isinstance(schema, dict):
            schema = {}
        schema = dict(schema)
        properties = dict(schema.get("properties", {}))
        for internal in ("_task_id", "agntid_task_id"):
            properties.pop(internal, None)
        schema["properties"] = properties
        required = [
            value
            for value in schema.get("required", [])
            if value not in {"_task_id", "agntid_task_id"}
        ]
        if required:
            schema["required"] = required
        else:
            schema.pop("required", None)

        async def call_tool(_mcp_name=mcp_name, **arguments):
            return await wrapped_client.call_tool_async(_mcp_name, arguments)

        converted.append(
            StructuredTool.from_function(
                coroutine=call_tool,
                name=name,
                description=description,
                args_schema=schema,
            )
        )
    return converted
