"""Pytest configuration for adaptyv tests."""

import os
import sys
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@pytest.fixture
def ada_api_key() -> str:
    """Get API key from environment."""
    key = os.environ.get("ADAPTYV_API_KEY")
    if not key:
        pytest.skip("ADAPTYV_API_KEY not set")
    return key


@pytest.fixture
def ada_client(ada_api_key: str):
    """FoundryClient using environment configuration.

    Reads BOTH ADAPTYV_API_KEY and ADAPTYV_API_URL from environment.
    The ada_api_key fixture ensures the key is present before proceeding.
    """
    from adaptyv.client.foundry import get_client

    return get_client()  # Reads both api_key and api_url from env


@pytest.fixture(autouse=True)
def reset_http_client():
    """Reset the shared HTTP client after each test.

    This prevents event loop issues when the client persists across tests.
    """
    yield
    # Reset after test completes
    try:
        from adaptyv.client.foundry import _client_cache

        _client_cache.clear()
    except ImportError:
        pass


def wait_for_experiment(client, experiment_id: str, timeout: float = 60.0) -> None:
    """Wait for experiment to become visible (eventual consistency).

    Args:
        client: FoundryClient instance.
        experiment_id: Experiment ID to wait for.
        timeout: Maximum wait time in seconds (default 60s).

    Raises:
        TimeoutError: If experiment not visible within timeout.
    """
    from adaptyv.exceptions import NotFoundError

    start = time.time()
    while time.time() - start < timeout:
        try:
            client.experiments.get(experiment_id)
            return  # Experiment is visible
        except NotFoundError:
            time.sleep(2)
        except Exception as e:
            # Log other errors but keep trying
            print(f"Unexpected error waiting for experiment: {e}")
            time.sleep(2)
    raise TimeoutError(f"Experiment {experiment_id} not visible after {timeout}s")
