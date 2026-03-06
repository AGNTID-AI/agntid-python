#!/usr/bin/env python3
"""
One-command quick test: connect to runtime, discover tools, run one tool call.

Prints:
  Connected to runtime
  Discovered N tools
  Tool call successful

Use this for copy → run smoke testing. Requires AGNTID_MCP_URL and a running
AgntID Runtime with at least one MCP tool (e.g. host add_numbers).

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

    async with agntid.AgntidMCPClient(url) as client:
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

            # Prefer add_numbers (host tool); else first available tool with safe args
            tool_name, args = None, {}
            for t in tools:
                if t.name in (agntid.TASK_OPEN_TOOL, agntid.TASK_CLOSE_TOOL):
                    continue
                if t.name == "add_numbers":
                    tool_name, args = "add_numbers", {"a": 2, "b": 3}
                    break
                if tool_name is None:
                    tool_name = t.name
                    if "path" in (t.inputSchema or {}).get("properties", {}):
                        args = {"path": "/tmp"}
                    elif "a" in (t.inputSchema or {}).get("properties", {}):
                        args = {"a": 1, "b": 2}

            if not tool_name:
                print("No runnable tool found", file=sys.stderr)
                sys.exit(1)

            await wrapped.call_tool_async(tool_name, args)
            print("Tool call successful")


if __name__ == "__main__":
    asyncio.run(main())
