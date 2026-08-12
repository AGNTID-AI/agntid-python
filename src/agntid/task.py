"""
Task lifecycle: create_task (task open) and close_task (task close).
SDK generates task_id; caller supplies agent_id, user_id, prompt.
Async helpers send_task_open and send_task_close invoke task glue over an MCP client.
Use task_context for automatic task_close on exit.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Callable, Mapping

from agntid.client import call_tool_async
from agntid._platform import (
    build_task_close_notification,
    build_task_close_tool_call,
    build_task_open_notification,
    build_task_open_tool_call,
    build_delegation_open_arguments,
    generate_task_id,
)

# Tool names for task open/close when using tools/call (spec 037)
TASK_OPEN_TOOL = "agntid_task_open"
TASK_CLOSE_TOOL = "agntid_task_close"
DELEGATION_OPEN_TOOL = "agntid_delegation_open"
DELEGATION_CLOSE_TOOL = "agntid_delegation_close"
ACTION_UPDATE_TOOL = "agntid_action_update"

# Type for sender: accepts a JSON-RPC message (dict) and sends it to the platform.
TaskSender = Callable[[dict[str, Any]], Any]


def task_open_arguments(
    task_id: str,
    agent_id: str,
    user_id: str,
    prompt: str,
    *,
    execution_context: Any | None = None,
) -> dict[str, Any]:
    """Build the public task-open argument object used by any MCP client."""
    arguments = {
        "task_id": task_id,
        "agent_id": agent_id.strip(),
        "user_id": user_id.strip(),
        "prompt": prompt.strip() if isinstance(prompt, str) else str(prompt),
    }
    if execution_context is not None:
        arguments["execution_context"] = (
            execution_context.to_dict()
            if hasattr(execution_context, "to_dict")
            else dict(execution_context)
        )
    return arguments


def delegation_open_arguments(
    task_id: str,
    delegation_context: Any,
) -> dict[str, Any]:
    """Build the public delegation-open argument object used by any MCP client."""
    return build_delegation_open_arguments(task_id, delegation_context)


async def send_task_open(
    client: Any,
    task_id: str,
    agent_id: str,
    user_id: str,
    prompt: str,
    *,
    execution_context: Any | None = None,
) -> Any:
    """
    Send task open to the runtime over an MCP client (tools/call agntid_task_open).
    Call once per run after create_task, before any other tool calls.

    :param client: MCP client with call_tool or call_tool_async.
    :returns: Server result (e.g. {"ok": true} or {"ok": false, "reason": "duplicate"}).
    """
    return await call_tool_async(
        client,
        TASK_OPEN_TOOL,
        task_open_arguments(
            task_id,
            agent_id,
            user_id,
            prompt,
            execution_context=execution_context,
        ),
    )


async def send_task_close(client: Any, task_id: str) -> Any:
    """
    Send task close to the runtime over an MCP client (tools/call agntid_task_close).
    Call when the run ends.

    :param client: MCP client with call_tool or call_tool_async.
    :returns: Server result (e.g. {"ok": true}).
    """
    return await call_tool_async(client, TASK_CLOSE_TOOL, {"task_id": task_id})


def parse_task_open_result(result: Any) -> tuple[bool, str]:
    """
    Interpret the result of send_task_open for success/failure.

    :param result: Raw result from send_task_open (dict or object with structured_content).
    :returns: (ok, message) — ok is True if task open was accepted; message is reason or empty.
    """
    result_dict = result if isinstance(result, dict) else getattr(result, "structured_content", None) or {}
    if not isinstance(result_dict, dict):
        return (True, "")
    if result_dict.get("ok") is False:
        return (False, str(result_dict.get("reason", result_dict)))
    return (True, "")


async def send_task_open_checked(
    client: Any,
    task_id: str,
    agent_id: str,
    user_id: str,
    prompt: str,
    *,
    execution_context: Any | None = None,
) -> tuple[bool, str]:
    """
    Send task open and return a simple (ok, message) for the caller to handle.

    :param client: MCP client with call_tool or call_tool_async.
    :returns: (ok, message) — ok is False if task open was rejected; message is the reason.
    """
    result = await send_task_open(
        client,
        task_id,
        agent_id,
        user_id,
        prompt,
        execution_context=execution_context,
    )
    return parse_task_open_result(result)


async def send_delegation_open(
    client: Any,
    task_id: str,
    delegation_context: Any,
) -> Any:
    """Open one canonical framework delegation below an existing root task."""
    return await call_tool_async(
        client,
        DELEGATION_OPEN_TOOL,
        delegation_open_arguments(task_id, delegation_context),
    )


async def send_delegation_close(
    client: Any,
    task_id: str,
    delegation_id: str,
    *,
    status: str = "completed",
    reason: str | None = None,
) -> Any:
    """Close one delegation without closing the root task."""
    return await call_tool_async(
        client,
        DELEGATION_CLOSE_TOOL,
        {
            "task_id": task_id,
            "delegation_id": delegation_id,
            "status": status,
            "reason": reason,
        },
    )


async def send_action_update(
    client: Any,
    task_id: str,
    action_id: str,
    status: str,
    **details: Any,
) -> Any:
    """Persist a declared action lifecycle transition."""
    arguments = {
        "task_id": task_id,
        "action_id": action_id,
        "status": status,
    }
    arguments.update(
        {
            key: value
            for key, value in details.items()
            if key
            in {
                "reason",
                "delegation_id",
                "acting_agent_id",
                "tool_name",
                "condition_status",
            }
            and value is not None
        }
    )
    return await call_tool_async(client, ACTION_UPDATE_TOOL, arguments)


@asynccontextmanager
async def task_context(client: Any, task_id: str):
    """
    Async context manager that sends task_close when the block exits (success or exception).
    Use so you don't have to remember to call send_task_close.

    Example:
        async with agntid.task_context(raw_client, task_id):
            # ... run agent ...
        # task_close is sent here automatically
    """
    try:
        yield
    finally:
        await send_task_close(client, task_id)


def create_task(
    agent_id: str,
    user_id: str,
    prompt: str,
    *,
    sender: TaskSender | None = None,
    use_tool_call: bool = True,
    execution_context: Mapping[str, Any] | Any | None = None,
) -> str:
    """
    Create (open) a task and return a new task_id. Sends task open to the platform.

    The SDK generates the task_id; the caller must not supply it. Use the returned
    task_id for all tool calls in this run and for close_task.

    :param agent_id: Agent identifier.
    :param user_id: Stable opaque user identifier (no PII).
    :param prompt: User prompt text (sent only here; not on tool traffic).
    :param sender: Callable that accepts one dict (JSON-RPC message) and sends it
        to the platform (e.g. over the MCP connection). Required for sending.
        Signature: sender(message: dict) -> None or result.
    :param use_tool_call: If True (default), use tools/call agntid_task_open form
        (works when MCP rejects custom notifications). If False, use agntid/task.open
        notification.
    :returns: New task identifier (opaque string).
    :raises ValueError: If agent_id, user_id, or prompt is empty.
    """
    if not (agent_id and agent_id.strip()):
        raise ValueError("agent_id must be non-empty")
    if not (user_id and user_id.strip()):
        raise ValueError("user_id must be non-empty")
    if prompt is None:
        raise ValueError("prompt must be provided")
    task_id = generate_task_id()
    if sender is not None:
        prompt_str = prompt.strip() if isinstance(prompt, str) else str(prompt)
        if use_tool_call:
            msg = build_task_open_tool_call(
                task_id,
                agent_id.strip(),
                user_id.strip(),
                prompt_str,
                execution_context,
            )
        else:
            msg = build_task_open_notification(
                task_id,
                agent_id.strip(),
                user_id.strip(),
                prompt_str,
                execution_context,
            )
        sender(msg)
    return task_id


def close_task(
    task_id: str,
    *,
    sender: TaskSender | None = None,
    use_tool_call: bool = True,
) -> None:
    """
    Close the task so the platform can finalize it (audit, cleanup). Idempotent.

    :param task_id: The task identifier returned from create_task for this run.
    :param sender: Same as create_task; callable that sends the JSON-RPC message.
    :param use_tool_call: If True (default), use tools/call agntid_task_close.
    """
    if sender is None:
        return
    if use_tool_call:
        msg = build_task_close_tool_call(task_id)
    else:
        msg = build_task_close_notification(task_id)
    sender(msg)
