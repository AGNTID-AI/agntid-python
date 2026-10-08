"""Typed task-intent results and prompt-aware tool filtering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
from typing import Any


class IntentPreparationError(RuntimeError):
    """The runtime did not return a usable task-scoped intent snapshot."""


@dataclass(frozen=True)
class TaskIntentSnapshot:
    """Framework-neutral projection of the runtime task-analysis snapshot."""

    snapshot_id: str = ""
    engine_id: str = ""
    engine_version: str = ""
    task_id: str = ""
    delegation_id: str = ""
    tasks: tuple[dict[str, Any], ...] = ()
    constraints: tuple[str, ...] = ()
    tool_assessments: tuple[dict[str, Any], ...] = ()
    relevant_tool_ids: tuple[str, ...] = ()
    relevant_tool_names: tuple[str, ...] = ()
    model: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaskIntentSnapshot":
        return cls(
            snapshot_id=str(value.get("id") or ""),
            engine_id=str(value.get("engine_id") or ""),
            engine_version=str(value.get("engine_version") or ""),
            task_id=str(value.get("task_id") or ""),
            delegation_id=str(value.get("delegation_id") or ""),
            tasks=_mapping_items(value.get("tasks")),
            constraints=_strings(value.get("constraints")),
            tool_assessments=_mapping_items(value.get("tool_assessments")),
            relevant_tool_ids=_strings(value.get("relevant_tool_ids")),
            relevant_tool_names=_strings(value.get("relevant_tool_names")),
            model=str(value.get("model") or ""),
            details=dict(value.get("details") or {})
            if isinstance(value.get("details"), Mapping)
            else {},
        )


@dataclass(frozen=True)
class TaskOpenResult:
    """Task-open outcome plus the runtime's optional intent preparation result."""

    ok: bool
    reason: str = ""
    intent_prepared: bool = False
    intent_reason: str = ""
    snapshot: TaskIntentSnapshot | None = None
    eligible_tool_count: int | None = None
    relevant_tool_count: int | None = None
    no_relevant_tools: bool | None = None


def parse_task_open_details(result: Any) -> TaskOpenResult:
    """Parse a task-open MCP result without discarding its intent snapshot."""

    payload = _result_mapping(result)
    if payload is None:
        return TaskOpenResult(ok=False, reason="invalid_task_open_result")

    intent = payload.get("intent")
    intent_data = dict(intent) if isinstance(intent, Mapping) else {}
    snapshot_value = intent_data.get("snapshot")
    snapshot = (
        TaskIntentSnapshot.from_mapping(snapshot_value)
        if isinstance(snapshot_value, Mapping)
        else None
    )

    return TaskOpenResult(
        ok=payload.get("ok") is True,
        reason=str(payload.get("reason") or ""),
        intent_prepared=intent_data.get("prepared") is True,
        intent_reason=str(intent_data.get("reason") or ""),
        snapshot=snapshot,
        eligible_tool_count=_optional_int(intent_data.get("eligible_tool_count")),
        relevant_tool_count=_optional_int(intent_data.get("relevant_tool_count")),
        no_relevant_tools=_optional_bool(intent_data.get("no_relevant_tools")),
    )


def filter_tools_for_task(
    tools: Sequence[Any],
    task_open: TaskOpenResult,
) -> list[Any]:
    """Return only tools shortlisted for this prompt, failing closed if unavailable.

    The runtime protection profile remains the upper bound. This function only
    narrows the already visible list; it never adds or authorizes a tool.
    """

    if not task_open.ok:
        raise IntentPreparationError(
            f"task open was rejected: {task_open.reason or 'unknown reason'}"
        )
    if not task_open.intent_prepared or task_open.snapshot is None:
        raise IntentPreparationError(
            "task intent was not prepared: "
            f"{task_open.intent_reason or 'no intent snapshot returned'}"
        )

    relevant = set(
        task_open.snapshot.relevant_tool_names
        or task_open.snapshot.relevant_tool_ids
    )
    return [tool for tool in tools if _tool_name(tool) in relevant]


def _tool_name(tool: Any) -> str:
    if isinstance(tool, Mapping):
        return str(tool.get("name") or "")
    return str(getattr(tool, "name", "") or "")


def _result_mapping(result: Any) -> dict[str, Any] | None:
    if isinstance(result, Mapping):
        return _unwrap_result(dict(result))

    for attribute in ("structured_content", "structuredContent"):
        value = getattr(result, attribute, None)
        if isinstance(value, Mapping):
            return _unwrap_result(dict(value))

    for block in getattr(result, "content", None) or ():
        text = (
            block.get("text")
            if isinstance(block, Mapping)
            else getattr(block, "text", None)
        )
        if not isinstance(text, str):
            continue
        try:
            value = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(value, Mapping):
            return _unwrap_result(dict(value))
    return None


def _unwrap_result(value: dict[str, Any]) -> dict[str, Any]:
    nested = value.get("result")
    if "ok" not in value and isinstance(nested, Mapping):
        return dict(nested)
    return value


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


def _mapping_items(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
