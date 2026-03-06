"""
Wire format for AgntID task glue (spec 037).
Builds task open and task close payloads for notifications or tool-call fallback.
"""

from __future__ import annotations

import uuid
from typing import Any


def generate_task_id() -> str:
    """Generate a new opaque task identifier (UUID). SDK always generates; caller never supplies."""
    return str(uuid.uuid4())


def build_task_open_notification(task_id: str, agent_id: str, user_id: str, prompt: str) -> dict[str, Any]:
    """Build JSON-RPC notification for agntid/task.open (spec 037 § 1.1)."""
    return {
        "jsonrpc": "2.0",
        "method": "agntid/task.open",
        "params": {
            "task_id": task_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "prompt": prompt,
        },
    }


def build_task_close_notification(task_id: str) -> dict[str, Any]:
    """Build JSON-RPC notification for agntid/task.close (spec 037 § 1.2)."""
    return {
        "jsonrpc": "2.0",
        "method": "agntid/task.close",
        "params": {"task_id": task_id},
    }


def build_task_open_tool_call(task_id: str, agent_id: str, user_id: str, prompt: str) -> dict[str, Any]:
    """Build tools/call for agntid_task_open fallback (spec 037 § 3). Use when notifications are rejected."""
    return {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "agntid_task_open",
            "arguments": {
                "task_id": task_id,
                "agent_id": agent_id,
                "user_id": user_id,
                "prompt": prompt,
            },
        },
        "id": None,  # Caller may set id for request/response; omit for fire-and-forget
    }


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
