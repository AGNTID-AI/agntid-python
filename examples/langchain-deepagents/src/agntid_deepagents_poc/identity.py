"""Trusted identity and per-prompt task context.

These values are deliberately outside the model-visible prompt. Production
callers should populate them from an authenticated request and deployment
configuration, not from text supplied by the end user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agntid import ExecutionPlan


@dataclass(frozen=True)
class DelegationPolicy:
    """Trusted application policy for one framework subagent."""

    acting_agent_id: str
    tool_allowlist: tuple[str, ...]
    agntid_tool_id_map: dict[str, str] = field(default_factory=dict)


@dataclass
class InvocationContext:
    """Identity and correlation data injected into one agent invocation."""

    agent_id: str
    user_id: str
    prompt: str
    task_id: str = field(default_factory=lambda: str(uuid4()))
    thread_id: str = field(default_factory=lambda: str(uuid4()))
    organization_id: str | None = None
    user_roles: tuple[str, ...] = ()
    prior_user_prompts: tuple[str, ...] = ()
    conversation_summary: str = ""
    active_constraints: tuple[str, ...] = ()
    revoked_intent_ids: tuple[str, ...] = ()
    entity_references: dict[str, Any] = field(default_factory=dict)
    execution_plan: ExecutionPlan | None = None
    delegation_policies: dict[str, DelegationPolicy] = field(default_factory=dict)
    approval_evidence: list[dict[str, Any]] = field(default_factory=list)
    open_delegations: dict[str, dict[str, Any]] = field(default_factory=dict)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    framework_events: list[dict[str, Any]] = field(default_factory=list)
    transport_events: list[dict[str, Any]] = field(default_factory=list)
    plan_action_states: dict[str, str] = field(default_factory=dict)
    plan_action_conditions: dict[str, str] = field(default_factory=dict)
    plan_action_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    condition_resolver: Callable[["InvocationContext", str, dict[str, Any]], list[dict[str, Any]]] | None = None
    action_output_projector: Callable[[str, dict[str, Any]], dict[str, Any] | None] | None = None
    reconciliation_attempts: int = 0
    reconciliation_pending_ids: tuple[str, ...] = ()

    def record_approval(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        decision: str,
        decision_id: str,
        operation_id: str = "",
        approver_id: str | None = None,
        source: str = "framework_interrupt",
        ttl_seconds: int = 300,
    ) -> None:
        """Record application-side HITL evidence for a later tool call."""

        issued_at = datetime.now(timezone.utc)
        self.approval_evidence.append(
            {
                "tool_name": tool_name,
                "arguments": dict(arguments),
                "required": True,
                "decision": decision,
                "decision_id": decision_id,
                "operation_id": operation_id,
                "approver_id": approver_id or self.user_id,
                "source": source,
                "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
                "expires_at": (issued_at + timedelta(seconds=ttl_seconds))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )

    def approval_for(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Return matching approval evidence without exposing it to the model."""

        for evidence in reversed(self.approval_evidence):
            if (
                evidence.get("tool_name") == tool_name
                and evidence.get("arguments") == arguments
            ):
                return {
                    key: evidence[key]
                    for key in (
                        "required",
                        "decision",
                        "approver_id",
                        "decision_id",
                        "operation_id",
                        "source",
                        "issued_at",
                        "expires_at",
                    )
                }
        return None
