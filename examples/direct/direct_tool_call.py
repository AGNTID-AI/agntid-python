#!/usr/bin/env python3
"""
One-command quick test: connect to runtime, discover tools, run one tool call.

Prints:
  Connected to runtime
  Discovered N tools
  Tool call successful

Use this for copy → run smoke testing. Requires AGNTID_MCP_URL and a running
AgntID Runtime with at least one MCP tool. Set AGNTID_ACCESS_TOKEN to the raw
OAuth access token when runtime client access requires authentication.

Usage:
  python examples/direct/direct_tool_call.py
"""

from __future__ import annotations

import asyncio
import os
import sys

# Allow running from repo root without pip install: python examples/direct/direct_tool_call.py
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_SCRIPT_DIR))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# Package may be in src/ (e.g. after pip install -e .)
_SRC = os.path.join(_REPO_ROOT, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import agntid


async def main() -> None:
    url = os.environ.get("AGNTID_MCP_URL", "http://localhost:8082/mcp")
    access_token = os.environ.get("AGNTID_ACCESS_TOKEN") or None

    async with agntid.AgntidMCPClient(url, access_token=access_token) as client:
        print("Connected to runtime")

        tools = await agntid.get_tools_list(client)
        print(f"Discovered {len(tools)} tools")

        wrapped = agntid.wrap_client(client)
        task_id = agntid.create_task("quick-test", "user-1", "smoke test")

        async with agntid.task_context(client, task_id):
            ok, msg = await agntid.send_task_open_checked(
                client, task_id, "quick-test", "user-1", "smoke test"
            )
            if not ok:
                print(f"Task open failed: {msg}", file=sys.stderr)
                sys.exit(1)

            wrapped.set_task_id(task_id)

            # Prefer the built-in demo tool; otherwise use the first tool whose
            # required arguments this smoke test understands.
            tool_name, args = None, {}
            for t in tools:
                if t.name in (agntid.TASK_OPEN_TOOL, agntid.TASK_CLOSE_TOOL):
                    continue
                if t.name == "demo_add_numbers":
                    tool_name, args = "demo_add_numbers", {
                        "first_number": 11,
                        "second_number": 22,
                    }
                    break
                if tool_name is None:
                    properties = (t.inputSchema or {}).get("properties", {})
                    required = set((t.inputSchema or {}).get("required", []))
                    if required <= {"path"} and "path" in properties:
                        tool_name, args = t.name, {"path": "/tmp"}
                    elif required <= {"first_number", "second_number"} and {
                        "first_number",
                        "second_number",
                    } <= properties.keys():
                        tool_name, args = t.name, {
                            "first_number": 11,
                            "second_number": 22,
                        }

            if not tool_name:
                print("No runnable tool found", file=sys.stderr)
                sys.exit(1)

            result = await wrapped.call_tool_async(tool_name, args)
            print(f"Tool call successful: {tool_name}")
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
