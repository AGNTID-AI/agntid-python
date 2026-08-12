import json

from agntid.context import arguments_digest
from agntid.decision import DecisionOutcome, ReviewStatus, parse_decision_from_exception
from agntid.denial import parse_denial_from_exception


def _exception():
    payload = {
        "__agntid_error": "AgntID policy review required",
        "__agntid_policy_decision": {
            "allowed": False,
            "reason": "Intent review pending: APPROVAL_REQUIRED",
            "correlation_id": "corr-123",
            "intent_validation": {
                "status": "review_required",
                "verdict": "review_required",
                "verdict_code": "APPROVAL_REQUIRED",
                "review": {
                    "review_id": "review-123",
                    "outcome": "review_required",
                    "status": "pending",
                    "resolution_code": "APPROVAL_REQUIRED",
                    "approval_source": "framework_interrupt",
                },
            },
        },
    }
    return ValueError("Error calling tool: " + json.dumps(payload))


def test_typed_review_decision_is_preserved():
    decision = parse_decision_from_exception(_exception())
    assert decision is not None
    assert decision.outcome is DecisionOutcome.REVIEW_REQUIRED
    assert decision.waiting_for_review
    assert decision.review is not None
    assert decision.review.status is ReviewStatus.PENDING
    assert decision.review.approval_source == "framework_interrupt"


def test_legacy_denial_parser_exposes_typed_review():
    message, info = parse_denial_from_exception(_exception())
    assert message.startswith("Tool call waiting for AgntID review")
    assert info["outcome"] == "review_required"
    assert info["review"].review_id == "review-123"


def test_argument_digest_is_order_independent():
    assert arguments_digest({"b": 2, "a": "one"}) == arguments_digest({"a": "one", "b": 2})
