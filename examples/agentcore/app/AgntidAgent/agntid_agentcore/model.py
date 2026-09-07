"""Lazy model construction keeps deterministic tests independent of AWS."""

from __future__ import annotations

from functools import lru_cache

from .config import Settings


@lru_cache(maxsize=4)
def _bedrock_model(model_id: str):
    from langchain_aws import ChatBedrock

    return ChatBedrock(model_id=model_id)


def load_model(settings: Settings):
    """Build the operator-selected model only for normal agent invocations."""

    return _bedrock_model(settings.model_id)
