"""Deep Agents lifecycle observer and declared-plan reconciliation.

This module is framework glue: it translates native ``task`` calls into the
framework-neutral AgntID delegation contract. Core AgntID remains independent
of LangChain and Deep Agents.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ToolCallRequest,
    hook_config,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphInterrupt

from .identity import InvocationContext


TERMINAL_ACTION_STATES = {
    "completed",
    "blocked",
    "failed",
    "skipped",
    "not_attempted",
}


class DeepAgentsExecutionObserver(AgentMiddleware):
    """Observe real subagent calls and keep required declared work honest."""

    def __init__(self, bridge: Any, *, max_reconciliation_attempts: int = 3):
        super().__init__()
        self.bridge = bridge
        self.max_reconciliation_attempts = max_reconciliation_attempts

    async def _record_framework_failure(
        self,
        context: InvocationContext,
        proposal: Any,
        close_delegation: Any,
        exc: BaseException,
    ) -> None:
        reason = f"Framework subagent failed: {type(exc).__name__}"
        await self.bridge.mark_action_for_agent(
            context,
            proposal.acting_agent_id,
            "failed",
            reason=reason,
            delegation_id=proposal.delegation_id,
        )
        await close_delegation(
            context,
            proposal,
            status="failed",
            reason=reason,
        )

    async def awrap_tool_call(self, request: ToolCallRequest, handler: Any) -> Any:
        if request.tool_call.get("name") != "task":
            return await handler(request)

        context = getattr(request.runtime, "context", None)
        if not isinstance(context, InvocationContext):
            return await handler(request)

        args = dict(request.tool_call.get("args") or {})
        subagent_type = str(args.get("subagent_type") or "").strip()
        description = str(args.get("description") or "").strip()
        tool_call_id = str(request.tool_call.get("id") or "")
        focus_description = getattr(self.bridge, "focus_task_description", None)
        ensure_delegation = getattr(self.bridge, "ensure_delegation", None)
        start_action = getattr(self.bridge, "start_action_for_agent", None)
        close_delegation = getattr(self.bridge, "close_delegation", None)
        if not all(
            callable(item)
            for item in (
                focus_description,
                ensure_delegation,
                start_action,
                close_delegation,
            )
        ):
            return await handler(request)
        focused_description = focus_description(
            context,
            subagent_type,
            description,
        )
        proposal = self.bridge.adapter.delegation_for_task_call(
            subagent_type=subagent_type,
            description=focused_description,
            tool_call_id=tool_call_id,
            context=context,
        )
        readiness = getattr(self.bridge, "action_readiness_for_agent", None)
        if callable(readiness):
            ready, reason = readiness(context, proposal.acting_agent_id)
            if not ready:
                context.framework_events.append(
                    {
                        "event": "delegation_deferred",
                        "framework": "langchain-deep-agents",
                        "framework_tool_call_id": tool_call_id,
                        "subagent_type": subagent_type,
                        "reason": reason,
                    }
                )
                return ToolMessage(
                    content=(
                        "AgntID execution-contract deferral: " + reason
                        + " Complete the prerequisite stage first, then retry this "
                        "delegation only if it remains required."
                    ),
                    name="task",
                    tool_call_id=tool_call_id,
                )
        await ensure_delegation(context, proposal)
        action_for_agent = getattr(self.bridge, "action_for_agent", None)
        action_id = (
            action_for_agent(context, proposal.acting_agent_id)
            if callable(action_for_agent)
            else None
        )
        await start_action(
            context,
            proposal.acting_agent_id,
            delegation_id=proposal.delegation_id,
        )
        context.framework_events.append(
            {
                "event": "delegation_started",
                "framework": "langchain-deep-agents",
                "framework_tool_call_id": tool_call_id,
                "subagent_type": subagent_type,
                "delegation_id": proposal.delegation_id,
                "description": focused_description,
            }
        )
        modified_call = {
            **request.tool_call,
            "args": {**args, "description": focused_description},
        }
        request = request.override(tool_call=modified_call)

        try:
            result = await handler(request)
        except GraphInterrupt:
            await self.bridge.mark_action_for_agent(
                context,
                proposal.acting_agent_id,
                "waiting",
                reason="The framework subagent is waiting for human or policy review.",
                delegation_id=proposal.delegation_id,
            )
            context.framework_events.append(
                {
                    "event": "delegation_waiting",
                    "delegation_id": proposal.delegation_id,
                    "subagent_type": subagent_type,
                }
            )
            raise
        except (BaseExceptionGroup, asyncio.CancelledError) as exc:
            await self._record_framework_failure(
                context,
                proposal,
                close_delegation,
                exc,
            )
            raise
        except Exception as exc:
            await self._record_framework_failure(
                context,
                proposal,
                close_delegation,
                exc,
            )
            raise

        action_status = (
            context.plan_action_states.get(action_id, "") if action_id else ""
        )
        if action_id and action_status not in TERMINAL_ACTION_STATES:
            reason = (
                "The framework subagent returned without completing its assigned "
                "required stage; supervisor reconciliation is required."
            )
            await self.bridge.mark_action_for_agent(
                context,
                proposal.acting_agent_id,
                "planned",
                reason=reason,
                delegation_id=proposal.delegation_id,
            )
            await close_delegation(
                context,
                proposal,
                status="not_attempted",
                reason=reason,
            )
            context.framework_events.append(
                {
                    "event": "delegation_incomplete",
                    "delegation_id": proposal.delegation_id,
                    "subagent_type": subagent_type,
                    "reason": reason,
                }
            )
            return result

        delegation_status = action_status or "completed"
        await close_delegation(context, proposal, status=delegation_status)
        context.framework_events.append(
            {
                "event": (
                    "delegation_completed"
                    if delegation_status == "completed"
                    else "delegation_finished"
                ),
                "delegation_id": proposal.delegation_id,
                "subagent_type": subagent_type,
                "status": delegation_status,
            }
        )
        return result

    @hook_config(can_jump_to=["model"])
    async def aafter_model(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        """Give the supervisor bounded chances to finish required plan stages."""
        context = getattr(runtime, "context", None)
        if not isinstance(context, InvocationContext) or context.execution_plan is None:
            return None
        messages = state.get("messages") or []
        if not messages:
            return None
        latest = messages[-1]
        if not isinstance(latest, AIMessage):
            return None
        if getattr(latest, "tool_calls", None):
            return None

        pending = []
        for action in context.execution_plan.actions:
            current = context.plan_action_states.get(action.action_id, action.status)
            if current in TERMINAL_ACTION_STATES:
                continue
            if action.kind == "response":
                # The host marks this complete after accepting the final response.
                continue
            if action.requirement == "optional":
                continue
            condition_status = context.plan_action_conditions.get(
                action.action_id, action.condition_status
            )
            if action.requirement == "conditional" and condition_status != "met":
                # The host resolver must first establish whether the condition applies.
                continue
            pending.append(action)
        if not pending:
            context.reconciliation_attempts = 0
            context.reconciliation_pending_ids = ()
            return None
        pending_ids = tuple(action.action_id for action in pending)
        if pending_ids != context.reconciliation_pending_ids:
            context.reconciliation_attempts = 0
            context.reconciliation_pending_ids = pending_ids
        if context.reconciliation_attempts >= self.max_reconciliation_attempts:
            return None

        context.reconciliation_attempts += 1
        checklist = "\n".join(
            f"- {action.title}: delegate to {action.expected_agent_id or 'the assigned specialist'}"
            for action in pending
        )
        return {
            "messages": [
                HumanMessage(
                    content=(
                        "Execution-contract check: required stages remain unresolved. "
                        "Continue the workflow before returning a final answer. Do not "
                        "repeat completed stages.\n" + checklist
                    )
                )
            ],
            "jump_to": "model",
        }
