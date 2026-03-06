#!/usr/bin/env python3
"""
OpenAI + FastMCP demo with AgntID task glue (no MSK / Semantic Kernel).

Uses the OpenAI Python client directly with function-calling to interact
with tools served through the AgntID MCP proxy. Each user prompt gets
its own task so the proxy can enforce policy and correlate tool calls.

Requires:
  pip install agntid-sdk openai
  export OPENAI_API_KEY=your-openai-api-key
  export AGNTID_MCP_URL=http://localhost:8082/mcp

Usage:
  python openai_demo.py                                        # defaults
  python openai_demo.py --agent-name MyAgent --user-id user-42 # custom
  python openai_demo.py --help
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Dev convenience: allow running from source tree without pip install.
_SDK_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "src",
)
if _SDK_SRC not in sys.path:
    sys.path.insert(0, _SDK_SRC)

import agntid

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="OpenAI + FastMCP demo with AgntID task glue.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--agent-name",
        default="DemoAgent",
        help="Name to register with AgntID (default: DemoAgent)",
    )
    ap.add_argument(
        "--user-id",
        default="demo-user",
        help="User ID for AgntID task attribution (default: demo-user)",
    )
    return ap.parse_args()

# ---------------------------------------------------------------------------
# OpenAI Chat Loop
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace):
    from openai import OpenAI

    env = agntid.require_env(
        "OPENAI_API_KEY",
        "AGNTID_MCP_URL",
        hint="pip install agntid-sdk openai",
    )
    mcp_url = env["AGNTID_MCP_URL"]
    registered_id = args.agent_name
    user_id = args.user_id
    chat_model = os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4o")

    openai_client = OpenAI()

    # -- 1. Connect to the AgntID MCP proxy ------------------------------------

    mcp_client = agntid.AgntidMCPClient(mcp_url)
    async with mcp_client:
        tools_list = await agntid.get_tools_list(mcp_client)
        wrapped = agntid.wrap_client(mcp_client)

        # Build OpenAI function definitions from MCP tools
        openai_tools, name_map = _mcp_tools_to_openai(tools_list)
        _print_banner(registered_id, user_id, tools_list)

        # -- 2. Prompt loop: one task per prompt --------------------------------

        messages: list[dict] = [
            {"role": "system", "content": "You are a helpful assistant. Use the available tools when needed."},
        ]

        while True:
            try:
                user_prompt = input("Your prompt: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_prompt:
                continue

            messages.append({"role": "user", "content": user_prompt})

            task_id = agntid.create_task(registered_id, user_id, user_prompt, sender=None)
            async with agntid.task_context(mcp_client, task_id):
                ok, msg = await agntid.send_task_open_checked(
                    mcp_client, task_id, registered_id, user_id, user_prompt,
                )
                if not ok:
                    print(f"[task] OPEN rejected: {msg}", file=sys.stderr)
                    continue
                wrapped.set_task_id(task_id)

                # Chat completion loop (handles multi-turn tool calls)
                assistant_msg = await _chat_loop(
                    openai_client, chat_model, messages, openai_tools, wrapped, name_map,
                )
                if assistant_msg:
                    print(f"OpenAI: {assistant_msg}")
                    messages.append({"role": "assistant", "content": assistant_msg})

                denial = agntid.get_last_denial(clear=True)
                if denial:
                    print(f"[policy] {agntid.format_denial(denial)}", file=sys.stderr)

            print()
            if not _ask_continue():
                break

        print("[openai_demo] Done.", file=sys.stderr)


async def _chat_loop(
    client,
    model: str,
    messages: list[dict],
    tools: list[dict],
    wrapped,
    name_map: dict[str, str],
) -> str | None:
    """
    Run the OpenAI chat completion loop, executing tool calls via the
    wrapped MCP client until the model produces a final text response.

    name_map translates OpenAI-safe names back to MCP names (e.g.
    awsS3_list_buckets -> awsS3.list_buckets).
    """
    while True:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools or None,
        )
        choice = response.choices[0]

        # Final text answer
        if choice.finish_reason != "tool_calls":
            return choice.message.content

        # Execute each tool call
        tool_calls = choice.message.tool_calls or []
        messages.append(choice.message.model_dump())

        for tc in tool_calls:
            openai_name = tc.function.name
            mcp_name = name_map.get(openai_name, openai_name)
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            print(f"  [Tool] {mcp_name}({json.dumps(fn_args)})", file=sys.stderr)
            try:
                result = await wrapped.call_tool_async(mcp_name, fn_args)
                result_str = _format_result(result)
            except Exception as exc:
                from agntid.denial import is_denial_error, parse_denial_from_exception, set_last_denial
                if is_denial_error(exc):
                    user_msg, denial_info = parse_denial_from_exception(exc)
                    if denial_info:
                        set_last_denial(mcp_name, denial_info)
                    else:
                        set_last_denial(mcp_name, {"reason": str(exc), "policy_name": ""})
                    # Brief message for the LLM — details shown separately after
                    result_str = user_msg
                else:
                    result_str = f"Error: {exc}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mcp_tools_to_openai(tools: list) -> tuple[list[dict], dict[str, str]]:
    """
    Convert MCP tool objects to OpenAI function-calling tool defs.

    Returns (openai_tools, name_map) where name_map maps OpenAI-safe
    names back to the original MCP names (e.g. awsS3_list_buckets -> awsS3.list_buckets).
    """
    exclude = {agntid.TASK_OPEN_TOOL, agntid.TASK_CLOSE_TOOL}
    result = []
    name_map: dict[str, str] = {}

    for t in tools:
        name = getattr(t, "name", None) or ""
        if name in exclude:
            continue

        # OpenAI requires function names to match ^[a-zA-Z0-9_-]+$
        safe_name = name.replace(".", "_")
        name_map[safe_name] = name

        desc = getattr(t, "description", None) or ""
        # First line only for the function description
        for line in desc.splitlines():
            line = line.strip()
            if line:
                desc = line
                break

        schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", None) or {}
        parameters = {
            "type": schema.get("type", "object"),
            "properties": schema.get("properties", {}),
        }
        if "required" in schema:
            parameters["required"] = schema["required"]

        result.append({
            "type": "function",
            "function": {
                "name": safe_name,
                "description": desc,
                "parameters": parameters,
            },
        })
    return result, name_map


def _format_result(result: object) -> str:
    """Return a string representation of a tool result."""
    if isinstance(result, dict):
        return json.dumps(result, default=str)
    return str(result)


def _print_banner(registered_id: str, user_id: str, tools: list) -> None:
    print()
    print("--- OpenAI + FastMCP + AgntID ---")
    print("Tools:")
    print(agntid.format_tools_display(tools, (agntid.TASK_OPEN_TOOL, agntid.TASK_CLOSE_TOOL)))
    print(f"Registered as: {registered_id}  User: {user_id}")
    print("One task per prompt; task_close sent automatically.")
    print("---")
    print()
    sys.stdout.flush()


def _ask_continue() -> bool:
    try:
        return input("Continue? (y/n): ").strip().lower() in ("y", "yes", "")
    except (EOFError, KeyboardInterrupt):
        print()
        return False

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    asyncio.run(run(parse_args()))

if __name__ == "__main__":
    main()
