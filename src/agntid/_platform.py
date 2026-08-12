"""
Wire format for AgntID task glue (spec 037).
Builds task open and task close payloads for notifications or tool-call fallback.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping


def _wire_context(value: Any | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise TypeError("execution context must be a mapping or expose to_dict()")
    return dict(value)


def generate_task_id() -> str:
    """Generate a new opaque task identifier (UUID). SDK always generates; caller never supplies."""
    return str(uuid.uuid4())


def build_task_open_notification(
    task_id: str,
    agent_id: str,
    user_id: str,
    prompt: str,
    execution_context: Any | None = None,
) -> dict[str, Any]:
    """Build JSON-RPC notification for agntid/task.open (spec 037 § 1.1)."""
    params = {
        "task_id": task_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "prompt": prompt,
    }
    if (wire_context := _wire_context(execution_context)) is not None:
        params["execution_context"] = wire_context
    return {
        "jsonrpc": "2.0",
        "method": "agntid/task.open",
        "params": params,
    }


def build_task_close_notification(task_id: str) -> dict[str, Any]:
    """Build JSON-RPC notification for agntid/task.close (spec 037 § 1.2)."""
    return {
        "jsonrpc": "2.0",
        "method": "agntid/task.close",
        "params": {"task_id": task_id},
    }


def build_task_open_tool_call(
    task_id: str,
    agent_id: str,
    user_id: str,
    prompt: str,
    execution_context: Any | None = None,
) -> dict[str, Any]:
    """Build tools/call for agntid_task_open fallback (spec 037 § 3). Use when notifications are rejected."""
    arguments = {
        "task_id": task_id,
        "agent_id": agent_id,
        "user_id": user_id,
        "prompt": prompt,
    }
    if (wire_context := _wire_context(execution_context)) is not None:
        arguments["execution_context"] = wire_context
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "agntid_task_open",
            "arguments": arguments,
        },
        "id": None,  # Caller may set id for request/response; omit for fire-and-forget
    }


def build_delegation_open_arguments(
    task_id: str, delegation_context: Any
) -> dict[str, Any]:
    """Build the canonical agntid_delegation_open argument object."""
    if hasattr(delegation_context, "to_dict"):
        delegation_context = delegation_context.to_dict()
    if not isinstance(delegation_context, Mapping):
        raise TypeError("delegation context must be a mapping or expose to_dict()")
    return {"task_id": task_id, **dict(delegation_context)}


def build_task_close_tool_call(task_id: str) -> dict[str, Any]:
    """Build tools/call for agntid_task_close fallback (spec 037 § 3)."""
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "agntid_task_close",
            "arguments": {"task_id": task_id},
        },
        "id": None,
    }
