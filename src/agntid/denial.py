"""
Policy and task denial parsing, storage, and formatting (framework-agnostic).

When the runtime denies a tool call (policy, intent, expired task), the error payload
contains JSON with __agntid_error and __agntid_policy_decision. This module extracts
meaningful fields and provides clean, human-readable messages for any agent framework.
"""

from __future__ import annotations

import json
import threading
from typing import Any


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_denial_error(exc: BaseException) -> bool:
    """True if the exception looks like a policy/denial/expired response from the platform."""
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in (
            "denied",
            "expired",
            "cannot be attributed",
            "request denied",
            "policy",
            "task expired",
            "task closed",
        )
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _extract_json_from_message(msg: str) -> dict[str, Any] | None:
    """
    Extract a JSON dict from an exception message. Handles:
      - Pure JSON: '{"__agntid_error": ...}'
      - Prefixed: "Error calling tool 'foo': {JSON}"
    Returns the parsed dict or None.
    """
    try:
        payload = json.loads(msg)
        return payload if isinstance(payload, dict) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    idx = msg.find("{")
    if idx > 0:
        try:
            payload = json.loads(msg[idx:])
            return payload if isinstance(payload, dict) else None
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return None


def parse_denial_from_exception(exc: BaseException) -> tuple[str, dict[str, Any] | None]:
    """
    Parse the runtime denial JSON from an exception. Extracts the meaningful fields
    and returns a clean one-line user_msg (not the raw JSON). Also returns structured
    denial_info for programmatic use.

    :param exc: The exception from a tool call.
    :returns: (user_facing_message, denial_info_dict_or_None).
    """
    msg = str(exc).strip()
    payload = _extract_json_from_message(msg)
    if payload is None:
        return (msg, None)
    err = payload.get("__agntid_error", "")
    policy = payload.get("__agntid_policy_decision")
    flow = payload.get("__agntid_execution_flow")
    if isinstance(policy, dict):
        reason = policy.get("reason") or err or "Policy denied"
        policy_name = policy.get("policy_name") or ""
        intent = policy.get("intent_validation") or {}
        denial_info: dict[str, Any] = {
            "reason": reason,
            "policy_name": policy_name,
            "error": err,
        }
        if intent.get("mismatch_reason"):
            denial_info["intent_mismatch"] = intent["mismatch_reason"]
        if isinstance(flow, dict) and flow.get("denial_step"):
            denial_info["denial_step"] = flow["denial_step"]
        parts = [f"Tool call denied: {reason}"]
        if policy_name:
            parts.append(f"Policy: {policy_name}")
        if intent.get("mismatch_reason"):
            parts.append(f"Intent: {intent['mismatch_reason']}")
        user_msg = ". ".join(parts) + "."
        return (user_msg, denial_info)
    if err:
        return (f"Tool call failed: {err}", None)
    return (msg, None)


# ---------------------------------------------------------------------------
# Thread-local storage (shared across frameworks)
# ---------------------------------------------------------------------------

_last_denial_local: threading.local = threading.local()


def _get_last_denial_storage() -> dict[str, Any]:
    if not hasattr(_last_denial_local, "value"):
        _last_denial_local.value = {}
    return _last_denial_local.value


def set_last_denial(tool_name: str, denial_info: dict[str, Any]) -> None:
    """Store the last denial so callers can retrieve it after a tool call."""
    storage = _get_last_denial_storage()
    storage["last_denial"] = {**denial_info, "tool": tool_name}


def get_last_denial(clear: bool = True) -> dict[str, Any] | None:
    """
    Return the last policy/task denial info captured from a tool call, if any.

    Works with any agent framework — not MSK-specific.

    :param clear: If True (default), clear the stored denial after returning.
    :returns: None or a dict with keys: "reason", "policy_name", "tool",
        and optionally "intent_mismatch", "denial_step", "error".
    """
    storage = _get_last_denial_storage()
    out = storage.get("last_denial")
    if clear and out is not None:
        storage["last_denial"] = None
    return out


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_denial(denial: dict[str, Any] | None) -> str | None:
    """
    Format a denial dict (from get_last_denial) as a clean, human-readable string.
    Returns None if denial is None.

    Example output:
        Tool "add_numbers" denied: Policy evaluation denied the request
          Policy: aws-agntid-awsS3.list_buckets-qktyxr
          Intent: action mismatch, resource mismatch
          Step: policy_evaluation
    """
    if denial is None:
        return None
    tool = denial.get("tool", "unknown")
    reason = denial.get("reason", "denied")
    lines = [f'Tool "{tool}" denied: {reason}']
    if denial.get("policy_name"):
        lines.append(f'  Policy: {denial["policy_name"]}')
    if denial.get("intent_mismatch"):
        lines.append(f'  Intent: {denial["intent_mismatch"]}')
    if denial.get("denial_step"):
        lines.append(f'  Step: {denial["denial_step"]}')
    return "\n".join(lines)
