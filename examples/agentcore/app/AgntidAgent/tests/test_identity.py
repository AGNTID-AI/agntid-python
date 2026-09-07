import pytest

from agntid_agentcore.errors import InvocationError
from agntid_agentcore.identity import (
    AUTHORIZATION_HEADER,
    USER_ID_HEADER,
    bearer_token,
    require_user_id,
)


def test_extracts_identity_case_insensitively():
    headers = {
        AUTHORIZATION_HEADER.lower(): "Bearer secret-token",
        USER_ID_HEADER.lower(): "user-42",
    }

    assert bearer_token(headers, required=True) == "secret-token"
    assert require_user_id(headers) == "user-42"


def test_rejects_missing_user_identity_instead_of_fabricating_it():
    with pytest.raises(InvocationError, match="Missing required header") as caught:
        require_user_id({})

    assert caught.value.status_code == 401


@pytest.mark.parametrize("value", ["token", "Basic abc", "Bearer", "Bearer a b"])
def test_rejects_invalid_bearer_header(value):
    with pytest.raises(InvocationError) as caught:
        bearer_token({AUTHORIZATION_HEADER: value}, required=True)

    assert caught.value.status_code == 401


def test_allows_missing_token_only_when_operator_disables_auth():
    assert bearer_token({}, required=False) is None
