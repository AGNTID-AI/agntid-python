"""LangChain Deep Agents extraction into the canonical AgentID contract.

The module intentionally uses structural access instead of importing LangChain,
so installing the base SDK does not pull a framework into other integrations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from agntid.adapters.base import AdapterCapabilities
from agntid.context import (
    ApprovalEvidence,
    ConversationContext,
    DelegatedIntent,
    DelegationContext,
    ExecutionContext,
    FrameworkInfo,
    extract_explicit_constraints,
    arguments_digest,
)

FRAMEWORK_NAME = "langchain-deep-agents"
ADAPTER_VERSION = "0.2.0"


@dataclass(frozen=True)
class DelegationProposal:
    cache_key: str
    framework_agent_name: str
    context: DelegationContext

    @property
    def delegation_id(self) -> str:
        return self.context.delegation_id

    @property
    def acting_agent_id(self) -> str:
        return self.context.acting_agent_id

    @property
    def parent_agent_id(self) -> str:
        return self.context.parent_agent_id

    @property
    def delegated_intent(self) -> str:
        return self.context.delegated_intent.text

    @property
    def tool_allowlist(self) -> tuple[str, ...]:
        return self.context.tool_allowlist

    @property
    def approval(self) -> dict[str, Any] | None:
        approval = self.context.approval
        return approval.to_dict() if approval.required else None


class DeepAgentsAdapter:
    framework_name = FRAMEWORK_NAME
    adapter_version = ADAPTER_VERSION
    capabilities = AdapterCapabilities(
        conversation_summary=True,
        delegation=True,
        approval_events=True,
        compound_intent=True,
        execution_plan=True,
        framework_delegation_events=True,
    )

    def execution_context(
        self,
        event: Any,
        *,
        task_id: str | None = None,
        agent_id: str | None = None,
    ) -> ExecutionContext:
        task_id = task_id or str(getattr(event, "task_id", "") or "")
        agent_id = agent_id or str(getattr(event, "agent_id", "") or "")
        if not task_id or not agent_id:
            raise ValueError("task_id and agent_id are required for root context")
        prior = [
            prompt.strip()
            for prompt in getattr(event, "prior_user_prompts", ())
            if prompt.strip()
        ]
        summary = str(getattr(event, "conversation_summary", "") or "").strip()
        if not summary and prior:
            summary = "Prior user requests: " + " | ".join(prior[-5:])

        constraints = list(getattr(event, "active_constraints", ()) or ())
        root_prompt = str(getattr(event, "prompt", "") or "")
        constraints.extend(extract_explicit_constraints(*prior, root_prompt))
        constraints = list(dict.fromkeys(item.strip() for item in constraints if item.strip()))

        organization_id = getattr(event, "organization_id", None)
        user_roles = tuple(getattr(event, "user_roles", ()) or ())
        extensions: dict[str, Any] = {}
        if organization_id or user_roles:
            extensions["agntid.langchain_deep_agents"] = {
                "organization_id": organization_id,
                "user_roles": list(user_roles),
            }

        return ExecutionContext(
            framework=FrameworkInfo(
                name=self.framework_name,
                adapter_version=self.adapter_version,
                capabilities=self.capabilities.names(),
            ),
            thread_id=str(getattr(event, "thread_id", "") or ""),
            turn_id=task_id,
            root_task_id=task_id,
            root_agent_id=agent_id,
            conversation=ConversationContext(
                summary=summary[: 8 * 1024],
                active_constraints=tuple(constraints[:100]),
                revoked_intent_ids=tuple(
                    getattr(event, "revoked_intent_ids", ()) or ()
                )[:100],
                entity_references=dict(
                    getattr(event, "entity_references", {}) or {}
                ),
            ),
            execution_plan=getattr(event, "execution_plan", None),
            extensions=extensions,
        )

    def delegation_context(self, event: Any) -> DelegationContext:
        if isinstance(event, DelegationContext):
            return event
        if not isinstance(event, dict):
            raise TypeError("delegation event must be a mapping")
        return DelegationContext.from_mapping(event)

    def delegation_for_task_call(
        self,
        *,
        subagent_type: str,
        description: str,
        tool_call_id: str,
        context: Any,
    ) -> DelegationProposal:
        """Translate an observed Deep Agents ``task`` call before tools run.

        This is intentionally separate from ``delegation_for_request`` so a
        reasoning-only, interrupted, or failed subagent is still observable.
        """
        policies = getattr(context, "delegation_policies", {}) or {}
        policy = policies.get(subagent_type)
        if policy is None:
            raise RuntimeError(
                f"Deep Agent {subagent_type!r} has no trusted AgentID delegation policy."
            )
        delegated_text = str(description or "").strip()
        if not delegated_text:
            raise RuntimeError("Deep Agents task calls require a delegated description.")
        cache_key = f"{subagent_type}\x1f{delegated_text}"
        task_id = str(getattr(context, "task_id"))
        canonical = DelegationContext(
            delegation_id=str(uuid5(NAMESPACE_URL, f"agntid:{task_id}:{cache_key}")),
            parent_agent_id=str(getattr(context, "agent_id")),
            acting_agent_id=policy.acting_agent_id,
            delegated_intent=DelegatedIntent(
                text=delegated_text[: 8 * 1024],
                source="langchain_deep_agents_task",
            ),
            tool_allowlist=tuple(
                policy.agntid_tool_id_map.get(name, name)
                for name in policy.tool_allowlist
            ),
            approval=ApprovalEvidence(),
        )
        return DelegationProposal(cache_key, subagent_type, canonical)

    def approval_for_request(
        self,
        *,
        request: Any,
        context: Any,
        policy: Any | None = None,
    ) -> ApprovalEvidence:
        """Bind host-recorded approval to this exact canonical tool call."""
        approval = getattr(context, "approval_for", lambda *_: None)(
            request.name, dict(request.args)
        )
        evidence = ApprovalEvidence.from_mapping(approval)
        if not evidence.required:
            return evidence

        if policy is None:
            policies = getattr(context, "delegation_policies", {}) or {}
            policy = next(
                (
                    candidate
                    for candidate in policies.values()
                    if request.name in getattr(candidate, "tool_allowlist", ())
                ),
                None,
            )
        tool_map = getattr(policy, "agntid_tool_id_map", {}) if policy else {}
        canonical_tool_name = tool_map.get(request.name, request.name)
        return replace(
            evidence,
            source=evidence.source or "framework_interrupt",
            tool_name=canonical_tool_name,
            arguments_digest=arguments_digest(dict(request.args)),
        )

    def delegation_for_request(self, *, request: Any, context: Any) -> DelegationProposal | None:
        runtime = getattr(request, "runtime", None)
        config = getattr(runtime, "config", {}) or {}
        metadata = config.get("metadata", {}) or {}
        framework_agent_name = metadata.get("lc_agent_name")
        policies = getattr(context, "delegation_policies", {}) or {}
        if not framework_agent_name:
            return None

        policy = policies.get(framework_agent_name)
        delegated_text = _delegated_intent_from_state(
            getattr(runtime, "state", {}) or {}, str(getattr(context, "prompt", "") or "")
        )
        if not delegated_text:
            if policy is None:
                # Deep Agents names the root agent too. A root call has no
                # distinct human task message and is correlated to the root.
                return None
            raise RuntimeError(
                f"Deep Agent {framework_agent_name!r} has no bounded delegated task description."
            )
        if policy is None:
            raise RuntimeError(
                f"Deep Agent {framework_agent_name!r} has no trusted AgentID delegation policy."
            )
        if request.name not in policy.tool_allowlist:
            raise RuntimeError(
                f"Deep Agent {framework_agent_name!r} is not allowed to call {request.name!r}."
            )

        cache_key = f"{framework_agent_name}\x1f{delegated_text}"
        task_id = str(getattr(context, "task_id"))
        approval_evidence = self.approval_for_request(
            request=request,
            context=context,
            policy=policy,
        )
        canonical = DelegationContext(
            delegation_id=str(uuid5(NAMESPACE_URL, f"agntid:{task_id}:{cache_key}")),
            parent_agent_id=str(getattr(context, "agent_id")),
            acting_agent_id=policy.acting_agent_id,
            delegated_intent=DelegatedIntent(
                text=delegated_text,
                source="langchain_deep_agents_task",
            ),
            tool_allowlist=tuple(
                policy.agntid_tool_id_map.get(name, name)
                for name in policy.tool_allowlist
            ),
            approval=approval_evidence,
        )
        return DelegationProposal(cache_key, framework_agent_name, canonical)


def _delegated_intent_from_state(state: Any, root_prompt: str) -> str:
    if not isinstance(state, dict):
        return ""
    candidates: list[str] = []
    messages = state.get("messages", [])
    for message in messages if isinstance(messages, list) else []:
        role = getattr(message, "type", None)
        content = getattr(message, "content", None)
        if isinstance(message, dict):
            role = message.get("type") or message.get("role")
            content = message.get("content")
        if role not in {"human", "user"}:
            continue
        text = _content_text(content).strip()
        if text and text != root_prompt.strip():
            candidates.append(text)
    return candidates[0][: 8 * 1024] if candidates else ""


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block if isinstance(block, str) else str(block.get("text") or "")
            for block in content
            if isinstance(block, str) or isinstance(block, dict)
        )
    return ""


__all__ = ["DeepAgentsAdapter", "DelegationProposal"]
