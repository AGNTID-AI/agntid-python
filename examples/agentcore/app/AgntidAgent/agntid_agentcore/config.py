"""Environment-backed configuration for the AgentCore application."""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str) -> frozenset[str]:
    raw = os.getenv(name, default)
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Operator-controlled settings; none are accepted from the user payload."""

    mcp_url: str
    agent_id: str
    tool_allowlist: frozenset[str]
    require_bearer: bool = True
    enable_direct_smoke: bool = False
    model_provider: str = "bedrock"
    model_id: str = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            mcp_url=os.getenv("AGNTID_MCP_URL", "http://localhost:8082/mcp").strip(),
            agent_id=os.getenv(
                "AGNTID_AGENT_ID", "aws-agentcore-langchain:v1"
            ).strip(),
            tool_allowlist=_csv("AGNTID_TOOL_ALLOWLIST", "demo_add_numbers"),
            require_bearer=_flag("AGNTID_REQUIRE_BEARER", True),
            enable_direct_smoke=_flag("AGNTID_ENABLE_DIRECT_SMOKE", False),
            model_provider=os.getenv("AGNTID_MODEL_PROVIDER", "bedrock")
            .strip()
            .lower(),
            model_id=os.getenv(
                "AGNTID_MODEL_ID",
                "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
            ).strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        parsed = urlparse(self.mcp_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AGNTID_MCP_URL must be an absolute HTTP(S) URL")
        if not self.agent_id:
            raise ValueError("AGNTID_AGENT_ID must not be empty")
        if not self.tool_allowlist:
            raise ValueError("AGNTID_TOOL_ALLOWLIST must contain at least one tool")
        if self.model_provider != "bedrock":
            raise ValueError("AGNTID_MODEL_PROVIDER currently supports only 'bedrock'")
        if not self.model_id:
            raise ValueError("AGNTID_MODEL_ID must not be empty")
