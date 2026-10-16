import importlib.util
from pathlib import Path


EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "direct" / "intent_shortlist.py"
SPEC = importlib.util.spec_from_file_location("intent_shortlist_example", EXAMPLE)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
shortlist_proof_warning = MODULE.shortlist_proof_warning


ELIGIBLE = {"demo_add_numbers", "intentDemo_send_email"}


def test_standard_intent_warns_that_shortlist_is_not_proven():
    warning = shortlist_proof_warning(
        engine_id="standard",
        eligible_count=2,
        relevant_count=2,
        constraints=(),
        eligible_names=ELIGIBLE,
        relevant_names=ELIGIBLE,
    )

    assert warning is not None
    assert "protected-call baseline only" in warning


def test_llm_intent_requires_reduction_constraints_and_prohibition_exclusion():
    warning = shortlist_proof_warning(
        engine_id="contextual",
        eligible_count=2,
        relevant_count=1,
        constraints=("Do not send any notification",),
        eligible_names=ELIGIBLE,
        relevant_names={"demo_add_numbers"},
    )

    assert warning is None


def test_llm_intent_warns_when_notification_tool_remains_visible():
    warning = shortlist_proof_warning(
        engine_id="contextual",
        eligible_count=3,
        relevant_count=2,
        constraints=("Do not send any notification",),
        eligible_names=ELIGIBLE | {"demo_get_ticket"},
        relevant_names=ELIGIBLE,
    )

    assert warning == "Notification-capable tools remain model-visible despite the prohibition."
