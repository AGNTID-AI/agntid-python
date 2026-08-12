"""Public port implemented by framework-specific AgentID adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agntid.context import DelegationContext, ExecutionContext


@dataclass(frozen=True)
class AdapterCapabilities:
    conversation_summary: bool = False
    delegation: bool = False
    nested_delegation: bool = False
    approval_events: bool = False
    compound_intent: bool = False
    execution_plan: bool = False
    framework_delegation_events: bool = False

    def names(self) -> tuple[str, ...]:
        return tuple(name for name, enabled in vars(self).items() if enabled)


@runtime_checkable
class AgentFrameworkAdapter(Protocol):
    framework_name: str
    adapter_version: str
    capabilities: AdapterCapabilities

    def execution_context(
        self, event: Any, *, task_id: str, agent_id: str
    ) -> ExecutionContext: ...

    def delegation_context(self, event: Any) -> DelegationContext: ...


def assert_adapter_identity(adapter: AgentFrameworkAdapter) -> None:
    if not isinstance(adapter, AgentFrameworkAdapter):
        raise AssertionError("adapter does not implement AgentFrameworkAdapter")
    if not adapter.framework_name.strip() or adapter.framework_name == "unknown":
        raise AssertionError("adapter.framework_name must be stable and non-generic")
    if not adapter.adapter_version.strip():
        raise AssertionError("adapter.adapter_version is required")
    if adapter.capabilities.nested_delegation and not adapter.capabilities.delegation:
        raise AssertionError("nested_delegation requires delegation capability")
