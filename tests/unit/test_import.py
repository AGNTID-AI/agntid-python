"""Smoke test: package imports and version."""
import pytest


def test_agntid_import():
    import agntid
    assert agntid is not None


def test_agntid_version():
    import agntid
    assert hasattr(agntid, "__version__")
    assert isinstance(agntid.__version__, str)
    assert len(agntid.__version__) >= 5  # e.g. "0.1.0"
