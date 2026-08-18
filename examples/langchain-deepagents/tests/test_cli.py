from agntid_deepagents_poc.cli import _exception_summary


def test_exception_summary_expands_nested_task_group_errors():
    error = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [RuntimeError("provider connection reset")],
    )

    rendered = _exception_summary(error)

    assert "ExceptionGroup: unhandled errors in a TaskGroup" in rendered
    assert "RuntimeError: provider connection reset" in rendered
