"""Typed, framework-neutral AgntID policy decision contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Any, Mapping


class DecisionOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW_REQUIRED = "review_required"
    UNKNOWN = "unknown"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ReviewDecision:
    review_id: str
    operation_id: str
    outcome: DecisionOutcome
    status: ReviewStatus
    resolution_code: str
    reason_code: str = ""
    reason_detail: str = ""
    approval_source: str = ""
    verification: str = ""
    decision_id: str = ""
    approver_id: str = ""
    tool_name: str = ""
    arguments_digest: str = ""
    requested_at: str = ""
    expires_at: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReviewDecision":
        data = dict(value)
        try:
            status = ReviewStatus(str(data.get("status") or "pending"))
        except ValueError:
            status = ReviewStatus.PENDING
        return cls(
            review_id=str(data.get("review_id") or ""),
            operation_id=str(data.get("operation_id") or data.get("correlation_id") or ""),
            outcome=_outcome(data.get("outcome")),
            status=status,
            resolution_code=str(data.get("resolution_code") or ""),
            reason_code=str(data.get("reason_code") or ""),
            reason_detail=str(data.get("reason_detail") or ""),
            approval_source=str(data.get("approval_source") or ""),
            verification=str(data.get("verification") or ""),
            decision_id=str(data.get("decision_id") or ""),
            approver_id=str(data.get("approver_id") or ""),
            tool_name=str(data.get("tool_name") or ""),
            arguments_digest=str(data.get("arguments_digest") or ""),
            requested_at=str(data.get("requested_at") or ""),
            expires_at=str(data.get("expires_at") or ""),
        )


@dataclass(frozen=True)
class AgntidDecision:
    outcome: DecisionOutcome
    allowed: bool
    reason: str = ""
    code: str = ""
    policy_name: str = ""
    correlation_id: str = ""
    intent_status: str = ""
    review: ReviewDecision | None = None

    @property
    def waiting_for_review(self) -> bool:
        return self.outcome is DecisionOutcome.REVIEW_REQUIRED


def parse_decision(payload: Mapping[str, Any]) -> AgntidDecision | None:
    """Parse either a policy decision or the wrapped FastMCP error envelope."""
    data = dict(payload)
    policy = data.get("__agntid_policy_decision", data)
    if not isinstance(policy, Mapping):
        return None
    intent = policy.get("intent_validation")
    intent = dict(intent) if isinstance(intent, Mapping) else {}
    review_data = intent.get("review")
    if not isinstance(review_data, Mapping):
        flow = data.get("__agntid_execution_flow")
        review_data = flow.get("review") if isinstance(flow, Mapping) else None
    review = ReviewDecision.from_mapping(review_data) if isinstance(review_data, Mapping) else None

    allowed = bool(policy.get("allowed", False))
    raw_outcome = intent.get("verdict")
    outcome = _outcome(raw_outcome)
    if review is not None:
        outcome = review.outcome
    elif outcome is DecisionOutcome.UNKNOWN:
        outcome = DecisionOutcome.ALLOW if allowed else DecisionOutcome.DENY

    return AgntidDecision(
        outcome=outcome,
        allowed=allowed,
        reason=str(intent.get("verdict_reason") or policy.get("reason") or data.get("__agntid_error") or ""),
        code=str(intent.get("verdict_code") or ""),
        policy_name=str(policy.get("policy_name") or ""),
        correlation_id=str(policy.get("correlation_id") or ""),
        intent_status=str(intent.get("status") or ""),
        review=review,
    )


def parse_decision_from_exception(exc: BaseException) -> AgntidDecision | None:
    payload = _extract_json(str(exc))
    return parse_decision(payload) if payload is not None else None


def _extract_json(message: str) -> dict[str, Any] | None:
    for candidate in (message.strip(), message[message.find("{") :] if "{" in message else ""):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _outcome(value: Any) -> DecisionOutcome:
    normalized = str(value or "").lower()
    if normalized in {"hitl", "review", "review_required"}:
        return DecisionOutcome.REVIEW_REQUIRED
    try:
        return DecisionOutcome(normalized)
    except ValueError:
        return DecisionOutcome.UNKNOWN


__all__ = [
    "AgntidDecision",
    "DecisionOutcome",
    "ReviewDecision",
    "ReviewStatus",
    "parse_decision",
    "parse_decision_from_exception",
]
