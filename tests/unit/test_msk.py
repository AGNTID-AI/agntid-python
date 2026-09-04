from agntid.msk import DEFAULT_EXCLUDE_TOOL_NAMES, sanitize_tool_name_for_msk


def test_msk_excludes_all_runtime_control_tools_by_default():
    assert set(DEFAULT_EXCLUDE_TOOL_NAMES) == {
        "agntid_task_open",
        "agntid_task_close",
        "agntid_delegation_open",
        "agntid_delegation_close",
        "agntid_action_update",
    }


def test_msk_sanitizes_mcp_tool_names():
    assert sanitize_tool_name_for_msk("demo.add_numbers") == "demo_add_numbers"
