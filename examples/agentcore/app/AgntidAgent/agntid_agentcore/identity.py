"""Extract trusted invocation identity without exposing bearer tokens."""

from __future__ import annotations

from collections.abc import Mapping

from .errors import InvocationError

CUSTOM_HEADER_PREFIX = "X-Amzn-Bedrock-AgentCore-Runtime-Custom-"
AUTHORIZATION_HEADER = f"{CUSTOM_HEADER_PREFIX}Agntid-Authorization"
USER_ID_HEADER = f"{CUSTOM_HEADER_PREFIX}Agntid-User-Id"


def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
    if not headers:
        return None
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def require_user_id(headers: Mapping[str, str] | None) -> str:
    """Read the stable user ID asserted by the trusted AgentCore invoker."""

    user_id = (_header(headers, USER_ID_HEADER) or "").strip()
    if not user_id:
        raise InvocationError(401, f"Missing required header: {USER_ID_HEADER}")
    if len(user_id) > 256 or any(ord(char) < 32 for char in user_id):
        raise InvocationError(400, "The AgntID user identifier is invalid.")
    return user_id


def bearer_token(
    headers: Mapping[str, str] | None,
    *,
    required: bool,
) -> str | None:
    """Return only the token value from the dedicated AgntID custom header."""

    raw = (_header(headers, AUTHORIZATION_HEADER) or "").strip()
    if not raw:
        if required:
            raise InvocationError(401, f"Missing required header: {AUTHORIZATION_HEADER}")
        return None
    scheme, separator, token = raw.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise InvocationError(401, "The AgntID authorization header must use Bearer authentication.")
    token = token.strip()
    if any(char.isspace() for char in token):
        raise InvocationError(401, "The AgntID bearer token is invalid.")
    return token
