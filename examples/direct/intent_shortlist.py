#!/usr/bin/env python3
"""Inspect runtime intent evidence, then make a protected call without a model."""

from __future__ import annotations

import asyncio
import os
import sys

import agntid


def shortlist_proof_warning(
    *,
    engine_id: str,
    eligible_count: int,
    relevant_count: int,
    constraints: tuple[str, ...],
    eligible_names: set[str],
    relevant_names: set[str],
) -> str | None:
    """Explain when this smoke cannot prove prompt-aware shortlisting."""
    notification_candidates = {
        name
        for name in eligible_names
        if "notification" in name.lower() or "send_email" in name.lower()
    }
    excluded_notifications = notification_candidates - relevant_names
    if engine_id.lower() == "standard":
        return (
            "Standard intent may keep the full eligible tool list and does not prove "
            "prohibition extraction. This run proves the protected-call baseline only; "
            "configure healthy LLM-based intent to demonstrate prompt-aware shortlisting."
        )
    if eligible_count <= relevant_count:
        return "The effective intent engine did not reduce the eligible tool list."
    if not constraints:
        return "The effective intent engine did not extract the prompt's prohibition."
    if not notification_candidates:
        return (
            "No notification or send-email tool was eligible, so this run cannot prove "
            "that the explicit prohibition removed one."
        )
    if not excluded_notifications:
        return "Notification-capable tools remain model-visible despite the prohibition."
    return None


async def main() -> None:
    prompt = "Add 11 and 22. Do not send any notification."
    url = os.environ.get("AGNTID_MCP_URL", "http://localhost:8082/mcp")
    token = os.environ.get("AGNTID_ACCESS_TOKEN") or None

    async with agntid.AgntidMCPClient(url, access_token=token) as client:
        visible_tools = await agntid.get_tools_list(client)
        task_id = agntid.create_task("intent-example", "user-1", prompt)
        wrapped = agntid.wrap_client(client, task_id)

        async with agntid.task_context(client, task_id):
            task_open = await agntid.send_task_open_details(
                client, task_id, "intent-example", "user-1", prompt
            )
            shortlisted = agntid.filter_tools_for_task(visible_tools, task_open)
            snapshot = task_open.snapshot
            assert snapshot is not None
            eligible_names = {tool.name for tool in visible_tools}
            relevant_names = {tool.name for tool in shortlisted}

            print(f"Intent engine: {snapshot.engine_id}")
            print(
                f"Tools: {task_open.eligible_tool_count} eligible -> "
                f"{task_open.relevant_tool_count} relevant"
            )
            for task in snapshot.tasks:
                print(f"Task: {task.get('instruction', '')}")
            for constraint in snapshot.constraints:
                print(f"Constraint: {constraint}")
            print(
                "Model-visible tools: "
                + (", ".join(tool.name for tool in shortlisted) or "(none)")
            )
            warning = shortlist_proof_warning(
                engine_id=snapshot.engine_id,
                eligible_count=task_open.eligible_tool_count,
                relevant_count=task_open.relevant_tool_count,
                constraints=snapshot.constraints,
                eligible_names=eligible_names,
                relevant_names=relevant_names,
            )
            if warning:
                print(f"WARNING: {warning}", file=sys.stderr)
            else:
                print("Prompt-aware shortlist proof: verified")

            if "demo_add_numbers" not in relevant_names:
                raise RuntimeError(
                    "demo_add_numbers was not shortlisted; enable the expected demo tool "
                    "and review the runtime intent configuration"
                )
            result = await wrapped.call_tool_async(
                "demo_add_numbers",
                {"first_number": 11, "second_number": 22},
            )
            print(f"Protected result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
