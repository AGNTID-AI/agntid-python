#!/usr/bin/env python3
"""Show task analysis and call only a prompt-shortlisted tool, without an LLM."""

from __future__ import annotations

import asyncio
import os

import agntid


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

            if "demo_add_numbers" not in {tool.name for tool in shortlisted}:
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
