"""Framework-neutral AgentID execution and delegation context.

These value objects are the public SDK representation of the version 1 wire
contract. Framework adapters translate their runtime events into these types;
the runtime never needs to import a framework package.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any, Mapping

CONTEXT_VERSION = "1.0"


def extract_explicit_constraints(*prompts: str) -> tuple[str, ...]:
    """Extract bounded, explicit negative constraints for any framework adapter.

    This is provenance capture, not authorization: the AgentID intent engine
    still parses and validates the root and delegated intents independently.
    """
    constraints: list[str] = []
    markers = ("do not ", "don't ", "never ", "must not ", "without ")
    for prompt in prompts:
        for sentence in re.split(r"(?<=[.!?;])\s+|\n+", prompt or ""):
            if any(marker in sentence.lower() for marker in markers):
                constraints.append(sentence.strip()[: 8 * 1024])
    return tuple(dict.fromkeys(item for item in constraints if item))[:100]


def _mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return deepcopy(dict(value or {}))


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
class ExecutionContext:
    framework: FrameworkInfo
    turn_id: str
    root_task_id: str
    root_agent_id: str
    thread_id: str = ""
    conversation: ConversationContext = field(default_factory=ConversationContext)
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "decision": self.decision,
            "approver_id": self.approver_id,
            "decision_id": self.decision_id,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ApprovalEvidence":
        data = dict(value or {})
        return cls(
            required=bool(data.get("required", False)),
            decision=str(data.get("decision") or ""),
            approver_id=str(data.get("approver_id") or ""),
            decision_id=str(data.get("decision_id") or ""),
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
