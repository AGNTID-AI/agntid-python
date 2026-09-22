#!/usr/bin/env python3
"""
MSK (Microsoft Semantic Kernel) demo with AgntID task glue.

Connects to the AgntID MCP proxy, registers one task per user prompt so
policy and audit see the correct intent, and runs an OpenAI-backed MSK
ChatCompletionAgent with automatic tool calling.

Requires:
  pip install agntid-sdk[msk]
  export OPENAI_API_KEY=your-openai-api-key
  export AGNTID_MCP_URL=http://localhost:8082/mcp
  export AGNTID_ACCESS_TOKEN=raw-access-token  # only when OAuth is required

Usage:
  python msk_demo.py                                        # defaults
  python msk_demo.py --agent-name MyAgent --user-id user-42 # custom
  python msk_demo.py --check-runtime                        # no model call
  python msk_demo.py --help
"""

from __future__ import annotations

import argparse
import asyncio
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
        description="MSK + OpenAI agent with AgntID task glue.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--agent-name",
        default="DemoAgent",
        help="Agent name for MSK and AgntID (default: DemoAgent)",
    )
    ap.add_argument(
        "--user-id",
        default="demo-user",
        help="User ID for AgntID task attribution (default: demo-user)",
    )
    ap.add_argument(
        "--check-runtime",
        action="store_true",
        help="Build the MSK plugin and verify demo_add_numbers without calling a model",
    )
    return ap.parse_args()

# ---------------------------------------------------------------------------
# MSK Chat Agent
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace):
    if args.check_runtime:
        await _check_runtime()
        return

    from semantic_kernel import Kernel
    from semantic_kernel.agents import ChatCompletionAgent
    from semantic_kernel.connectors.ai import FunctionChoiceBehavior
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
    from semantic_kernel.functions import KernelArguments

    # -- 1. MSK kernel + OpenAI ------------------------------------------------

    env = agntid.require_env(
        "OPENAI_API_KEY",
        "AGNTID_MCP_URL",
        hint="pip install agntid-sdk[msk]",
    )
    mcp_url = env["AGNTID_MCP_URL"]
    access_token = os.environ.get("AGNTID_ACCESS_TOKEN") or None
    user_id = args.user_id

    kernel = Kernel()
    chat_model = os.environ.get("OPENAI_CHAT_MODEL_ID", "gpt-4o")
    kernel.add_service(OpenAIChatCompletion(ai_model_id=chat_model, service_id="chat"))
    settings = kernel.get_prompt_execution_settings_from_service_id(service_id="chat")
    settings.function_choice_behavior = FunctionChoiceBehavior.Auto()

    chat_agent = ChatCompletionAgent(
        kernel=kernel,
        name=args.agent_name,
        instructions="You are a helpful assistant. Use the available tools when needed.",
        arguments=KernelArguments(settings=settings),
    )

    # -- 2. AgntID: connect, list tools, add plugin ---------------------------

    mcp_client = agntid.AgntidMCPClient(
        mcp_url,
        access_token=access_token,
    )
    async with mcp_client:
        tools_list = await agntid.get_tools_list(mcp_client)
        wrapped = agntid.wrap_client(mcp_client)

        plugin = agntid.msk.create_plugin_from_mcp_tools(
            wrapped,
            tools_list,
            plugin_name="MCPTools",
        )
        kernel.add_plugin(plugin, plugin_name="MCPTools")

        registered_id = agntid.msk.agent_id_from_agent(chat_agent)
        _print_banner(registered_id, user_id, tools_list)

        # -- 3. Prompt loop: one task per prompt --------------------------------

        thread = None
        while True:
            try:
                user_prompt = input("Your prompt: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_prompt:
                continue

            task_id = agntid.create_task(registered_id, user_id, user_prompt, sender=None)
            async with agntid.task_context(mcp_client, task_id):
                ok, msg = await agntid.send_task_open_checked(
                    mcp_client, task_id, registered_id, user_id, user_prompt,
                )
                if not ok:
                    print(f"[task] OPEN rejected: {msg}", file=sys.stderr)
                    continue
                wrapped.set_task_id(task_id)

                try:
                    async for response in chat_agent.invoke(
                        messages=user_prompt,
                        thread=thread,
                        arguments=KernelArguments(settings=settings),
                    ):
                        print(f"MSK: {response.content}")
                        thread = response.thread
                except Exception as exc:
                    print(f"MSK error: {exc}", file=sys.stderr)

                denial = agntid.get_last_denial(clear=True)
                if denial:
                    print(f"[policy] {agntid.format_denial(denial)}", file=sys.stderr)

            print()
            if not _ask_continue():
                break

        print("[msk_demo] Done.", file=sys.stderr)


async def _check_runtime() -> None:
    """Verify MCP discovery and MSK plugin construction without a model call."""

    from semantic_kernel import Kernel

    env = agntid.require_env(
        "AGNTID_MCP_URL",
        hint='pip install -e ".[msk]"',
    )
    access_token = os.environ.get("AGNTID_ACCESS_TOKEN") or None
    async with agntid.AgntidMCPClient(
        env["AGNTID_MCP_URL"],
        access_token=access_token,
    ) as client:
        tools = await agntid.get_tools_list(client)
        wrapped = agntid.wrap_client(client)
        plugin = agntid.msk.create_plugin_from_mcp_tools(
            wrapped,
            tools,
            plugin_name="MCPTools",
        )
        Kernel().add_plugin(plugin, plugin_name="MCPTools")

    tool_names = {getattr(tool, "name", "") for tool in tools}
    if "demo_add_numbers" not in tool_names:
        raise RuntimeError(
            "demo_add_numbers is not visible; review the runtime protection profile"
        )
    print(
        "MSK readiness passed: demo_add_numbers is visible and the MCPTools "
        "plugin was built without calling a model."
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_banner(registered_id: str, user_id: str, tools: list) -> None:
    print()
    print("--- MSK + MCP + AgntID ---")
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
    try:
        asyncio.run(run(parse_args()))
    except Exception as exc:
        print(f"[msk_demo] Failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

if __name__ == "__main__":
    main()
