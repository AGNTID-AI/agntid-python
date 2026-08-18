"""Command-line entry point for all three POCs."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from rich.console import Console
from rich.panel import Panel

from .bridge import AgntidBridge
from .display import print_event
from .identity import InvocationContext
from .operations_agent import (
    OPERATIONS_DELEGATION_POLICIES,
    build_operations_deep_agent,
    build_operations_execution_plan,
    project_operations_action_output,
    resolve_operations_conditions,
)
from .operations_demo import (
    run_engineering_demo,
    run_interactive_turn,
    run_safe_delegation_smoke,
)
from .runners import run_framework_agent

DEFAULT_MCP_URL = "http://agntid.ai:8082/mcp"


def _exception_summary(exc: BaseException, *, limit: int = 12) -> str:
    """Render nested task-group failures without an unreadable traceback."""

    lines: list[str] = []

    def visit(error: BaseException, depth: int) -> None:
        if len(lines) >= limit:
            return
        message = str(error).strip() or "(no message)"
        lines.append(f"{'  ' * depth}{type(error).__name__}: {message}")
        if isinstance(error, BaseExceptionGroup):
            for child in error.exceptions:
                visit(child, depth + 1)

    visit(exc, 0)
    if len(lines) >= limit:
        lines.append("Additional nested errors omitted.")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AgntID + LangChain/Deep Agents end-to-end POCs"
    )
    parser.add_argument(
        "--mcp-url", default=os.getenv("AGNTID_MCP_URL", DEFAULT_MCP_URL)
    )
    parser.add_argument("--agent-id", default=os.getenv("AGENT_ID", "deepagents-demo-agent"))
    parser.add_argument("--user-id", default=os.getenv("USER_ID", "demo-user"))

    commands = parser.add_subparsers(dest="command", required=True)

    direct = commands.add_parser("direct", help="No LLM: prove task and policy flow")
    direct.add_argument("--first", type=float, default=11)
    direct.add_argument("--second", type=float, default=22)

    commands.add_parser(
        "identity-matrix",
        help="Same agent, two users: one allowed and one denied execution",
    )

    smoke = commands.add_parser(
        "framework-smoke",
        help="Deterministic prompt-to-agent-to-AgntID flow; no model API key",
    )
    smoke.add_argument("--framework", choices=("langchain", "deepagents"), required=True)
    smoke.add_argument("--first", type=float, default=11)
    smoke.add_argument("--second", type=float, default=22)

    engineering = commands.add_parser(
        "engineering-demo",
        help="Realistic planned/subagent/security scenarios against local AgntID",
    )
    engineering.add_argument("--state-dir", default=".demo_state")

    safe_delegation = commands.add_parser(
        "delegation-smoke",
        help="Safe compound prompt through two subagents; no mutating tools",
    )
    safe_delegation.add_argument("--state-dir", default=".demo_state")

    ops_chat = commands.add_parser(
        "ops-chat",
        help="Interactive memory + subagents + approval Deep Agent chat",
    )
    ops_chat.add_argument("--model", default=os.getenv("MODEL", "openai:gpt-4.1-mini"))
    ops_chat.add_argument("--state-dir", default=".demo_state")
    ops_chat.add_argument("--organization-id", default="demo-platform-org")
    ops_chat.add_argument("--roles", default="incident-operator")
    ops_chat.add_argument(
        "--verbose-boundary",
        action="store_true",
        help="Print the full framework-to-AgntID boundary diagnostics after each turn",
    )

    for name in ("langchain", "deepagents"):
        agent = commands.add_parser(name, help=f"Run the {name} agent POC")
        agent.add_argument("prompt", nargs="?", default="Please add 11 and 22")
        agent.add_argument("--model", default=os.getenv("MODEL", "openai:gpt-4.1-mini"))
    return parser


async def _direct(args: argparse.Namespace, console: Console) -> None:
    prompt = f"Add {args.first:g} and {args.second:g}"
    context = InvocationContext(args.agent_id, args.user_id, prompt)
    async with AgntidBridge(args.mcp_url).connect() as bridge:
        event = await bridge.invoke_direct(
            "demo_add_numbers",
            {"first_number": args.first, "second_number": args.second},
            context,
        )
    print_event(console, event)


async def _identity_matrix(args: argparse.Namespace, console: Console) -> None:
    cases = (
        ("alice@example", 22.0, "expected allow"),
        ("bob@example", 32.0, "expected policy denial"),
    )
    async with AgntidBridge(args.mcp_url).connect() as bridge:
        for user_id, second, expectation in cases:
            prompt = f"Add 11 and {second:g}"
            context = InvocationContext(args.agent_id, user_id, prompt)
            console.rule(f"{user_id} - {expectation}")
            event = await bridge.invoke_direct(
                "demo_add_numbers",
                {"first_number": 11, "second_number": second},
                context,
            )
            print_event(console, event)


async def _agent(args: argparse.Namespace, console: Console) -> None:
    # The CLI values demonstrate the flow. A web service must set user_id from
    # its verified auth subject and agent_id from trusted deployment config.
    context = InvocationContext(args.agent_id, args.user_id, args.prompt)
    async with AgntidBridge(args.mcp_url).connect() as bridge:
        answer, events = await run_framework_agent(
            framework=args.command,
            model=args.model,
            bridge=bridge,
            context=context,
        )
    console.print(Panel(answer, title=f"{args.command} answer"))
    for event in events:
        print_event(console, event)


class _ToolCallingFakeModel(FakeMessagesListChatModel):
    """A deterministic model used only to verify framework tool plumbing."""

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self


async def _framework_smoke(args: argparse.Namespace, console: Console) -> None:
    prompt = f"Please add {args.first:g} and {args.second:g}"
    model = _ToolCallingFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "demo_add_numbers",
                        "args": {
                            "first_number": args.first,
                            "second_number": args.second,
                        },
                        "id": "deterministic-demo-call",
                    }
                ],
            ),
            AIMessage(content="The protected arithmetic tool call completed."),
        ]
    )
    context = InvocationContext(args.agent_id, args.user_id, prompt)
    async with AgntidBridge(args.mcp_url).connect() as bridge:
        answer, events = await run_framework_agent(
            framework=args.framework,
            model=model,
            bridge=bridge,
            context=context,
        )
    console.print(Panel(answer, title=f"{args.framework} deterministic answer"))
    for event in events:
        print_event(console, event)


async def _engineering_demo(args: argparse.Namespace, console: Console) -> None:
    async with AgntidBridge(args.mcp_url).connect() as bridge:
        await run_engineering_demo(
            console=console,
            bridge=bridge,
            state_root=Path(args.state_dir).resolve(),
            agent_id=args.agent_id,
            user_id=args.user_id,
        )


async def _delegation_smoke(args: argparse.Namespace, console: Console) -> None:
    async with AgntidBridge(args.mcp_url).connect() as bridge:
        await run_safe_delegation_smoke(
            console=console,
            bridge=bridge,
            state_root=Path(args.state_dir).resolve(),
            agent_id=args.agent_id,
            user_id=args.user_id,
        )


async def _ops_chat(args: argparse.Namespace, console: Console) -> None:
    thread_id = str(uuid4())
    prior_user_prompts: list[str] = []
    roles = tuple(role.strip() for role in args.roles.split(",") if role.strip())
    async with AgntidBridge(args.mcp_url).connect() as bridge:
        agent = build_operations_deep_agent(
            model=args.model,
            bridge=bridge,
            state_root=Path(args.state_dir).resolve(),
            require_approval=True,
        )
        console.print(
            Panel(
                "Persistent operations chat started. Type 'exit' to stop.\n"
                f"Thread: {thread_id}\nMemory: {Path(args.state_dir).resolve() / 'memories' / 'AGENTS.md'}",
                title="AgntID Deep Agent",
            )
        )
        while True:
            prompt = console.input("\n[bold cyan]you>[/bold cyan] ").strip()
            if prompt.lower() in {"exit", "quit"}:
                return
            if not prompt:
                continue
            context = InvocationContext(
                agent_id=args.agent_id,
                user_id=args.user_id,
                prompt=prompt,
                thread_id=thread_id,
                organization_id=args.organization_id,
                user_roles=roles,
                prior_user_prompts=tuple(prior_user_prompts[-5:]),
                delegation_policies=dict(OPERATIONS_DELEGATION_POLICIES),
            )
            context.execution_plan = build_operations_execution_plan(
                prompt, context.task_id
            )
            context.condition_resolver = resolve_operations_conditions
            context.action_output_projector = project_operations_action_output
            try:
                await run_interactive_turn(
                    console=console,
                    agent=agent,
                    bridge=bridge,
                    context=context,
                    verbose_boundary=args.verbose_boundary,
                )
            except Exception as exc:
                console.print(
                    Panel(
                        _exception_summary(exc)
                        + "\n\nThis turn failed, but the chat is still active. "
                        "You may retry the prompt or continue.",
                        title="Agent turn failed",
                        border_style="red",
                    )
                )
            prior_user_prompts.append(prompt)


async def _run(args: argparse.Namespace, console: Console) -> None:
    if args.command == "direct":
        await _direct(args, console)
    elif args.command == "identity-matrix":
        await _identity_matrix(args, console)
    elif args.command == "framework-smoke":
        await _framework_smoke(args, console)
    elif args.command == "engineering-demo":
        await _engineering_demo(args, console)
    elif args.command == "delegation-smoke":
        await _delegation_smoke(args, console)
    elif args.command == "ops-chat":
        await _ops_chat(args, console)
    else:
        await _agent(args, console)


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = _parser().parse_args(argv)
    console = Console()
    try:
        asyncio.run(_run(args, console))
    except Exception as exc:
        console.print(
            Panel(_exception_summary(exc), title="POC failed", border_style="red")
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
