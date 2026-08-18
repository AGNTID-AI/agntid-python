"""Terminal rendering for business output and AgntID audit attribution."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table


def message_text(message_or_content: Any) -> str:
    """Render provider-native message blocks as normal terminal text."""

    content = getattr(message_or_content, "content", message_or_content)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_blocks: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_blocks.append(str(block.get("text", "")))
            elif getattr(block, "type", None) == "text":
                text_blocks.append(str(getattr(block, "text", "")))
        if text_blocks:
            return "\n".join(text for text in text_blocks if text)
    return str(content)


def print_event(console: Console, event: dict[str, Any]) -> None:
    status = event.get("status") or "unknown"
    color = "green" if status == "success" else "red" if status == "denied" else "yellow"
    table = Table(show_header=False, box=None)
    for label, key in (
        ("Status", "status"),
        ("Agent", "agent_id"),
        ("User", "user_id"),
        ("Identity shown from", "identity_evidence"),
        ("Calling subagent", "deep_agent_name"),
        ("Task", "task_id"),
        ("Tool", "tool"),
        ("Policy", "policy"),
        ("Policy allowed", "policy_allowed"),
        ("Event", "event_id"),
        ("Correlation", "correlation_id"),
        ("Runtime", "runtime_id"),
        ("Snapshot", "snapshot_id"),
        ("Intent verdict", "intent_verdict"),
        ("Intent confidence", "intent_confidence"),
        ("Intent reason", "intent_reason"),
        ("Waiting on", "waiting_on"),
        ("AgntID review", "review_id"),
        ("Review status", "review_status"),
        ("Approval source", "review_source"),
        ("Approval verification", "review_verification"),
        ("Denial", "denial_reason"),
    ):
        value = event.get(key)
        if value is not None:
            table.add_row(label, str(value))
    console.print(Panel(table, title=f"AgntID execution [{color}]{status}[/{color}]"))
    if event.get("result") is not None:
        console.print(Panel(JSON.from_data(event["result"]), title="Business result"))
