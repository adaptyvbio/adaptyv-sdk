"""Pytest configuration for adaptyv tests."""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@pytest.fixture(autouse=True)
def reset_http_client():
    """Reset the shared HTTP client after each test.

    This prevents event loop issues when the client persists across tests.
    """
    yield
    # Reset after test completes
    try:
        from adaptyv.client.http import reset_async_client

        reset_async_client()
    except ImportError:
        pass
