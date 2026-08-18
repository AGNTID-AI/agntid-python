"""Parse and summarize the structured result envelope returned by AgntID."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


def _text_parts(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return

    content = getattr(value, "content", value)
    if not isinstance(content, list):
        return

    for block in content:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            yield block["text"]
        elif isinstance(getattr(block, "text", None), str):
            yield block.text


def _json_object_from_text(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def parse_payload(value: Any) -> dict[str, Any] | None:
    """Extract the first JSON object from MCP or LangChain tool output."""

    structured = getattr(value, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    for text in _text_parts(value):
        parsed = _json_object_from_text(text)
        if parsed is not None:
            return parsed
    return None


def summarize_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Return the small set of business and audit fields useful in a demo."""

    flow = envelope.get("__agntid_execution_flow") or {}
    result = envelope.get("__agntid_result")
    policy = envelope.get("__agntid_policy_decision") or {}

    if not policy:
        for step in flow.get("steps", []):
            if step.get("step") == "policy_evaluation":
                policy = step.get("details") or {}
                break

    summary: dict[str, Any] = {
        "status": flow.get("status"),
        "tool": flow.get("tool_name"),
        "task_id": flow.get("session_id"),
        "event_id": flow.get("event_id"),
        "correlation_id": flow.get("correlation_id"),
        "policy": policy.get("policy_name"),
        "policy_allowed": policy.get("allowed"),
        "denial_reason": flow.get("denial_reason") or envelope.get("__agntid_error"),
        "result": result,
    }

    intent = policy.get("intent_validation") or {}
    review = intent.get("review") or flow.get("review") or {}
    facts = policy.get("intent_facts") or {}
    actor = facts.get("actor") or policy.get("actor_context") or {}
    summary.update(
        {
            "agent_id": actor.get("agent_id"),
            "user_id": actor.get("user_id"),
            "identity_evidence": "agntid_response" if actor else "invocation_context",
            "intent_confidence": intent.get("confidence"),
            "intent_verdict": intent.get("verdict") or intent.get("status"),
            "intent_reason": (
                intent.get("verdict_reason")
                or intent.get("reason")
                or intent.get("error")
            ),
            "runtime_id": (policy.get("runtime_context") or {}).get("runtime_id"),
            "snapshot_id": policy.get("snapshot_id"),
        }
    )
    if review:
        summary.update(
            {
                "review_id": review.get("review_id"),
                "review_status": review.get("status"),
                "review_outcome": review.get("outcome"),
                "review_source": review.get("approval_source"),
                "review_verification": review.get("verification"),
            }
        )
    if flow.get("waiting_on"):
        summary["waiting_on"] = flow["waiting_on"]
    return summary
