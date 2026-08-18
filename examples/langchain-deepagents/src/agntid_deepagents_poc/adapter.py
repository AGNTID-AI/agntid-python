"""Compatibility re-export; the maintained adapter lives in agntid-python."""

from agntid.adapters.langchain_deep_agents import (
    DeepAgentsAdapter,
    DelegationProposal,
)

__all__ = ["DeepAgentsAdapter", "DelegationProposal"]
