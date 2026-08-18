import json

from agntid_deepagents_poc.results import parse_payload, summarize_envelope


def test_parse_payload_handles_success_content_blocks():
    envelope = {
        "__agntid_execution_flow": {
            "status": "success",
            "tool_name": "demo.add_numbers",
            "session_id": "task-1",
            "event_id": "audit-1",
            "correlation_id": "corr-1",
            "steps": [
                {
                    "step": "policy_evaluation",
                    "details": {"allowed": True, "policy_name": "addition-policy"},
                }
            ],
        },
        "__agntid_result": {"result": 33.0},
    }
    blocks = [{"type": "text", "text": json.dumps(envelope)}]

    assert parse_payload(blocks) == envelope
    assert summarize_envelope(envelope) == {
        "status": "success",
        "tool": "demo.add_numbers",
        "task_id": "task-1",
        "event_id": "audit-1",
        "correlation_id": "corr-1",
        "policy": "addition-policy",
        "policy_allowed": True,
        "denial_reason": None,
        "result": {"result": 33.0},
        "agent_id": None,
        "user_id": None,
        "identity_evidence": "invocation_context",
        "intent_confidence": None,
        "intent_verdict": None,
        "intent_reason": None,
        "runtime_id": None,
        "snapshot_id": None,
    }


def test_parse_payload_handles_adapter_error_prefix_and_denial_identity():
    envelope = {
        "__agntid_execution_flow": {
            "status": "denied",
            "tool_name": "demo.add_numbers",
            "session_id": "task-2",
            "denial_reason": "range denied",
        },
        "__agntid_policy_decision": {
            "allowed": False,
            "policy_name": "addition-policy",
            "intent_facts": {
                "actor": {"agent_id": "agent-1", "user_id": "user-2"}
            },
        },
    }
    blocks = [
        {
            "type": "text",
            "text": f"Error executing tool demo_add_numbers: {json.dumps(envelope)}",
        }
    ]

    parsed = parse_payload(blocks)
    assert parsed == envelope
    summary = summarize_envelope(parsed)
    assert summary["status"] == "denied"
    assert summary["agent_id"] == "agent-1"
    assert summary["user_id"] == "user-2"
    assert summary["denial_reason"] == "range denied"
