"""
Microsoft Semantic Kernel (MSK) integration for AgntID.

Provides create_plugin_from_mcp_tools so MSK users can add MCP tools to a Kernel
with minimal code. Handles MSK-specific quirks (e.g. function name pattern
^[0-9A-Za-z_-]+$) inside the SDK so customer code stays simple.

agent_id_from_agent(agent) derives an agent_id from an MSK agent (e.g. ChatCompletionAgent.name).
user_id cannot be derived from Kernel; the application must supply it (e.g. from auth/session).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from agntid.client import get_tools_list
from agntid.denial import (
    format_denial,
    get_last_denial,
    is_denial_error,
    parse_denial_from_exception,
    set_last_denial,
)
from agntid.mcp_wrapper import wrap_client
from agntid.task import send_task_open

# Task-glue tool names to exclude from the plugin (not callable by the LLM)
AGNTID_TASK_OPEN = "agntid_task_open"
AGNTID_TASK_CLOSE = "agntid_task_close"
AGNTID_DELEGATION_OPEN = "agntid_delegation_open"
AGNTID_DELEGATION_CLOSE = "agntid_delegation_close"
AGNTID_ACTION_UPDATE = "agntid_action_update"
DEFAULT_EXCLUDE_TOOL_NAMES = (
    AGNTID_TASK_OPEN,
    AGNTID_TASK_CLOSE,
    AGNTID_DELEGATION_OPEN,
    AGNTID_DELEGATION_CLOSE,
    AGNTID_ACTION_UPDATE,
)


def agent_id_from_agent(agent: Any) -> str:
    """
    Derive an agent_id from an MSK agent (e.g. ChatCompletionAgent).
    Uses agent.name or agent.id if present; otherwise returns a default.

    Kernel itself has no id field; use this with the agent instance after creation.
    """
    out = getattr(agent, "name", None) or getattr(agent, "id", None)
    return (out.strip() if isinstance(out, str) and out.strip() else None) or "msk-agent"


def user_id_from_kernel(kernel: Any) -> str | None:
    """
    Kernel has no built-in user concept. Returns None; the application must
    supply user_id from auth/session (e.g. request.user.id or session token).
    """
    return None


def sanitize_tool_name_for_msk(name: str) -> str:
    """
    Sanitize an MCP tool name for MSK's KernelFunctionMetadata (pattern ^[0-9A-Za-z_-]+$).
    Replaces any character not in [0-9A-Za-z_-] with underscore (e.g. awsS3.create_bucket -> awsS3_create_bucket).
    """
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in (name or ""))


def _tool_name(tool: Any) -> str:
    """Get tool name from MCP tool object (attribute or dict)."""
    if isinstance(tool, dict):
        return (tool.get("name") or "") or ""
    return (getattr(tool, "name", None) or "") or ""


def _allowed_param_keys(tool: Any) -> set[str] | None:
    """Allowed argument names from tool inputSchema.properties. None = allow all."""
    schema = getattr(tool, "inputSchema", None) if not isinstance(tool, dict) else tool.get("inputSchema")
    if not schema or not isinstance(schema, dict):
        return None
    props = schema.get("properties")
    if not props or not isinstance(props, dict):
        return None
    return set(props.keys())


def _build_kernel_param_list(tool: Any) -> list[dict[str, Any]]:
    """Build MSK __kernel_function_parameters__ from tool inputSchema for correct LLM schema per tool."""
    schema = getattr(tool, "inputSchema", None) if not isinstance(tool, dict) else tool.get("inputSchema")
    if not schema or not isinstance(schema, dict):
        return []
    props = schema.get("properties")
    required = schema.get("required")
    if not isinstance(props, dict):
        return []
    if not isinstance(required, list):
        required = []
    out = []
    for param_name, param_schema in props.items():
        if not isinstance(param_schema, dict):
            param_schema = {}
        desc = param_schema.get("description") or param_schema.get("title") or ""
        type_str = param_schema.get("type", "string")
        if isinstance(type_str, list):
            type_str = type_str[0] if type_str else "string"
        out.append({
            "name": param_name,
            "description": desc,
            "type_": type_str,
            "is_required": param_name in required,
            "default_value": param_schema.get("default"),
        })
    return out


def _format_mcp_result(result: Any) -> str:
    """Extract readable text from MCP tool result."""
    if result is None:
        return ""
    if isinstance(result, dict) and "content" in result:
        items = result["content"]
        if items and isinstance(items[0], dict) and "text" in items[0]:
            return str(items[0]["text"])
    if isinstance(result, dict) and "result" in result:
        r = result["result"]
        if isinstance(r, list) and r and isinstance(r[0], dict) and "text" in r[0]:
            return str(r[0]["text"])
    return str(result)


def create_plugin_from_mcp_tools(
    wrapped_client: Any,
    tools: list[Any],
    *,
    plugin_name: str = "MCPTools",
    exclude_tool_names: tuple[str, ...] = DEFAULT_EXCLUDE_TOOL_NAMES,
) -> Any:
    """
    Build an MSK plugin from an AgntID-wrapped MCP client and list of MCP tools.

    Use this after agntid.wrap_client(client, task_id). The returned plugin can be
    added to a Kernel with kernel.add_plugin(plugin, plugin_name=plugin_name).
    Handles MSK function name sanitization (e.g. dots -> underscores) and per-tool
    parameter schema from inputSchema so the LLM sees correct tool definitions.

    :param wrapped_client: The result of agntid.wrap_client(mcp_client, task_id).
    :param tools: List of MCP tools (e.g. from client.list_tools()). Can be objects
        with .name, .description, .inputSchema or dicts with those keys.
    :param plugin_name: Name for the plugin when adding to the kernel.
    :param exclude_tool_names: Tool names to omit from the plugin (e.g. task glue).
    :returns: An MSK plugin instance (object with kernel_function methods). Add to
        kernel with kernel.add_plugin(plugin, plugin_name=plugin_name).

    Requires the semantic-kernel package (e.g. ``pip install agntid-sdk[msk]``).
    """
    from semantic_kernel.functions import kernel_function

    # Filter out task-glue and other excluded tools
    agent_tools = [t for t in tools if _tool_name(t) not in exclude_tool_names]

    seen_sanitized: dict[str, str] = {}
    methods: dict[str, Any] = {}

    for tool in agent_tools:
        original_name = _tool_name(tool) or str(tool)
        sanitized = sanitize_tool_name_for_msk(original_name)
        base = sanitized
        if sanitized in seen_sanitized and seen_sanitized[sanitized] != original_name:
            n = 1
            while sanitized in seen_sanitized:
                sanitized = f"{base}_{n}"
                n += 1
        seen_sanitized[sanitized] = original_name

        desc = (
            getattr(tool, "description", None) if not isinstance(tool, dict) else tool.get("description")
        ) or f"Call MCP tool: {original_name}"
        allowed_keys = _allowed_param_keys(tool)
        param_metadata = _build_kernel_param_list(tool)

        def _make_fn(
            mcp_tool_name: str,
            msk_name: str,
            tool_desc: str,
            allowed_param_keys: set[str] | None,
            param_list: list[dict[str, Any]],
        ):
            @kernel_function(name=msk_name, description=tool_desc)
            async def _tool_fn(self: Any, **kwargs: Any) -> str:
                if allowed_param_keys is not None:
                    kwargs = {k: v for k, v in kwargs.items() if k in allowed_param_keys}
                print(f"  [Tool] {mcp_tool_name}({json.dumps(kwargs, default=str)})", file=sys.stderr)
                try:
                    result = await self._client.call_tool_async(mcp_tool_name, kwargs)
                    return _format_mcp_result(result)
                except BaseException as e:
                    if is_denial_error(e):
                        user_msg, denial_info = parse_denial_from_exception(e)
                        if denial_info:
                            set_last_denial(mcp_tool_name, denial_info)
                        else:
                            set_last_denial(mcp_tool_name, {"reason": str(e), "policy_name": ""})
                        return user_msg
                    raise

            _tool_fn.__name__ = msk_name
            _tool_fn.__kernel_function_parameters__ = param_list
            return _tool_fn

        methods[sanitized] = _make_fn(original_name, sanitized, desc, allowed_keys, param_metadata)

    class _MCPPlugin:
        """MSK plugin: each method calls the wrapped MCP client (task_id added by AgntID wrapper)."""
        def __init__(self, client: Any) -> None:
            self._client = client

    for attr_name, method in methods.items():
        setattr(_MCPPlugin, attr_name, method)

    return _MCPPlugin(wrapped_client)


async def mcp_plugin_for_task(
    client: Any,
    task_id: str,
    agent_id: str,
    user_id: str,
    prompt: str,
    *,
    plugin_name: str = "MCPTools",
    exclude_tool_names: tuple[str, ...] = DEFAULT_EXCLUDE_TOOL_NAMES,
) -> tuple[Any, list[Any], Any]:
    """
    One-shot: send task open, wrap client, fetch tools, build MSK plugin.
    Use when you have a connected MCP client and want a plugin for this task.

    :param client: Connected MCP client (e.g. fastmcp Client, already in async with).
    :param task_id: From create_task for this run.
    :param agent_id: Agent identifier.
    :param user_id: User identifier (from your app; Kernel has no user).
    :param prompt: User prompt for this run (sent with task open).
    :param plugin_name: Name for the plugin when adding to the kernel.
    :param exclude_tool_names: Tool names to omit from the plugin.
    :returns: (plugin, tools_list, open_result). Check open_result with
        agntid.parse_task_open_result(open_result) for (ok, message).
    """
    open_result = await send_task_open(client, task_id, agent_id, user_id, prompt)
    wrapped = wrap_client(client, task_id)
    tools_list = await get_tools_list(client)
    plugin = create_plugin_from_mcp_tools(
        wrapped,
        tools_list,
        plugin_name=plugin_name,
        exclude_tool_names=exclude_tool_names,
    )
    return (plugin, tools_list, open_result)
