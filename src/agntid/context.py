"""Framework-neutral AgentID execution and delegation context.

These value objects are the public SDK representation of the version 1 wire
contract. Framework adapters translate their runtime events into these types;
the runtime never needs to import a framework package.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Mapping

CONTEXT_VERSION = "1.0"


def extract_explicit_constraints(*prompts: str) -> tuple[str, ...]:
    """Extract bounded, unconditional negative constraints for adapters.

    This is provenance capture, not authorization: the AgentID intent engine
    still parses and validates the root and delegated intents independently.

    Conditional branches are deliberately excluded. Flattening text such as
    ``Otherwise, do not notify anyone`` into ``active_constraints`` would turn
    the false branch of a condition into a turn-wide prohibition even after the
    condition was verified as true.
    """
    constraints: list[str] = []
    markers = ("do not ", "don't ", "never ", "must not ", "without ")
    conditional_markers = (
        "if ",
        "if and only if ",
        "only if ",
        "unless ",
        "otherwise",
        "else ",
        "except when ",
        "only when ",
        "when ",
    )
    for prompt in prompts:
        for sentence in re.split(r"(?<=[.!?;])\s+|\n+", prompt or ""):
            lowered = sentence.lower().strip()
            if not any(marker in lowered for marker in markers):
                continue
            if any(marker in lowered for marker in conditional_markers):
                continue
            constraints.append(sentence.strip()[: 8 * 1024])
    return tuple(dict.fromkeys(item for item in constraints if item))[:100]


def _mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return deepcopy(dict(value or {}))


def arguments_digest(arguments: Mapping[str, Any] | None) -> str:
    """Stable SHA-256 binding shared with the AgntID runtime."""
    canonical = json.dumps(
        dict(arguments or {}), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class FrameworkInfo:
    name: str
    adapter_version: str
    capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "adapter_version": self.adapter_version,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class ConversationContext:
    summary: str = ""
    active_constraints: tuple[str, ...] = ()
    revoked_intent_ids: tuple[str, ...] = ()
    entity_references: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "active_constraints": list(self.active_constraints),
            "revoked_intent_ids": list(self.revoked_intent_ids),
            "entity_references": deepcopy(self.entity_references),
        }


@dataclass(frozen=True)
class PlannedAction:
    """A framework-declared action visible even if no tool is attempted."""

    action_id: str
    title: str
    kind: str = "tool"
    tool_name: str = ""
    expected_agent_id: str = ""
    description: str = ""
    status: str = "planned"
    reason: str = ""
    requirement: str = "required"
    condition: str = ""
    condition_status: str = ""
    depends_on: tuple[str, ...] = ()
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "title": self.title,
            "kind": self.kind,
            "tool_name": self.tool_name,
            "expected_agent_id": self.expected_agent_id,
            "description": self.description,
            "status": self.status,
            "reason": self.reason,
            "requirement": self.requirement,
            "condition": self.condition,
            "condition_status": self.condition_status,
            "depends_on": list(self.depends_on),
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    """Framework-neutral plan-versus-execution manifest."""

    plan_id: str
    actions: tuple[PlannedAction, ...]
    source: str = "framework_adapter"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "source": self.source,
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True)
class ExecutionContext:
    framework: FrameworkInfo
    turn_id: str
    root_task_id: str
    root_agent_id: str
    thread_id: str = ""
    conversation: ConversationContext = field(default_factory=ConversationContext)
    execution_plan: ExecutionPlan | None = None
    extensions: dict[str, Any] = field(default_factory=dict)
    version: str = CONTEXT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "framework": self.framework.to_dict(),
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "root_task_id": self.root_task_id,
            "root_agent_id": self.root_agent_id,
            "conversation": self.conversation.to_dict(),
            "execution_plan": (
                self.execution_plan.to_dict() if self.execution_plan else None
            ),
            "extensions": deepcopy(self.extensions),
        }

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        task_id: str,
        agent_id: str,
    ) -> "ExecutionContext":
        data = dict(value)
        framework = dict(data.get("framework") or {})
        conversation = dict(data.get("conversation") or {})
        return cls(
            version=str(data.get("version") or CONTEXT_VERSION),
            framework=FrameworkInfo(
                name=str(framework.get("name") or "unknown"),
                adapter_version=str(framework.get("adapter_version") or ""),
                capabilities=tuple(framework.get("capabilities") or ()),
            ),
            thread_id=str(data.get("thread_id") or ""),
            turn_id=str(data.get("turn_id") or task_id),
            root_task_id=str(data.get("root_task_id") or task_id),
            root_agent_id=str(data.get("root_agent_id") or agent_id),
            conversation=ConversationContext(
                summary=str(conversation.get("summary") or ""),
                active_constraints=tuple(conversation.get("active_constraints") or ()),
                revoked_intent_ids=tuple(conversation.get("revoked_intent_ids") or ()),
                entity_references=_mapping(conversation.get("entity_references")),
            ),
            execution_plan=(
                ExecutionPlan(
                    plan_id=str(dict(data["execution_plan"]).get("plan_id") or ""),
                    source=str(
                        dict(data["execution_plan"]).get("source")
                        or "framework_adapter"
                    ),
                    actions=tuple(
                        PlannedAction(
                            action_id=str(item.get("action_id") or ""),
                            title=str(item.get("title") or ""),
                            kind=str(item.get("kind") or "tool"),
                            tool_name=str(item.get("tool_name") or ""),
                            expected_agent_id=str(
                                item.get("expected_agent_id") or ""
                            ),
                            description=str(item.get("description") or ""),
                            status=str(item.get("status") or "planned"),
                            reason=str(item.get("reason") or ""),
                            requirement=str(item.get("requirement") or "required"),
                            condition=str(item.get("condition") or ""),
                            condition_status=str(item.get("condition_status") or ""),
                            depends_on=tuple(item.get("depends_on") or ()),
                            sequence=int(item.get("sequence") or 0),
                        )
                        for item in dict(data["execution_plan"]).get("actions", [])
                    ),
                )
                if data.get("execution_plan")
                else None
            ),
            extensions=_mapping(data.get("extensions")),
        )


@dataclass(frozen=True)
class DelegatedIntent:
    text: str
    action: str = ""
    resource: str = ""
    scope: dict[str, Any] = field(default_factory=dict)
    constraints: tuple[str, ...] = ()
    source: str = "framework_delegation"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "action": self.action,
            "resource": self.resource,
            "scope": deepcopy(self.scope),
            "constraints": list(self.constraints),
            "source": self.source,
        }


@dataclass(frozen=True)
class ApprovalEvidence:
    required: bool = False
    decision: str = ""
    approver_id: str = ""
    decision_id: str = ""
    operation_id: str = ""
    source: str = ""
    tool_name: str = ""
    arguments_digest: str = ""
    issued_at: str = ""
    expires_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "decision": self.decision,
            "approver_id": self.approver_id,
            "decision_id": self.decision_id,
            "operation_id": self.operation_id,
            "source": self.source,
            "tool_name": self.tool_name,
            "arguments_digest": self.arguments_digest,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ApprovalEvidence":
        data = dict(value or {})
        return cls(
            required=bool(data.get("required", False)),
            decision=str(data.get("decision") or ""),
            approver_id=str(data.get("approver_id") or ""),
            decision_id=str(data.get("decision_id") or ""),
            operation_id=str(data.get("operation_id") or ""),
            source=str(data.get("source") or ""),
            tool_name=str(data.get("tool_name") or ""),
            arguments_digest=str(data.get("arguments_digest") or ""),
            issued_at=str(data.get("issued_at") or ""),
            expires_at=str(data.get("expires_at") or ""),
        )


@dataclass(frozen=True)
class DelegationContext:
    delegation_id: str
    parent_agent_id: str
    acting_agent_id: str
    delegated_intent: DelegatedIntent
    parent_delegation_id: str = ""
    tool_allowlist: tuple[str, ...] = ()
    approval: ApprovalEvidence = field(default_factory=ApprovalEvidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "parent_delegation_id": self.parent_delegation_id,
            "parent_agent_id": self.parent_agent_id,
            "acting_agent_id": self.acting_agent_id,
            "delegated_intent": self.delegated_intent.to_dict(),
            "tool_allowlist": list(self.tool_allowlist),
            "approval": self.approval.to_dict(),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DelegationContext":
        data = dict(value)
        intent = dict(data.get("delegated_intent") or {})
        if not str(intent.get("text") or "").strip():
            raise ValueError("delegated_intent.text must be non-empty")
        return cls(
            delegation_id=str(data.get("delegation_id") or ""),
            parent_delegation_id=str(data.get("parent_delegation_id") or ""),
            parent_agent_id=str(data.get("parent_agent_id") or ""),
            acting_agent_id=str(data.get("acting_agent_id") or ""),
            delegated_intent=DelegatedIntent(
                text=str(intent["text"]),
                action=str(intent.get("action") or ""),
                resource=str(intent.get("resource") or ""),
                scope=_mapping(intent.get("scope")),
                constraints=tuple(intent.get("constraints") or ()),
                source=str(intent.get("source") or "framework_delegation"),
            ),
            tool_allowlist=tuple(data.get("tool_allowlist") or ()),
            approval=ApprovalEvidence.from_mapping(data.get("approval")),
        )
