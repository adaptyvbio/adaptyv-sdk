"""Real integration tests against Foundry API.

Run with: pytest tests/test_integration.py -v -s

Requirements:
- ADAPTYV_API_KEY in .env or environment
- For write tests: API key must have create_experiment permission

Tests FAIL LOUDLY if permissions are missing - no silent passes.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

# Load .env file before importing SDK (to set ADAPTYV_API_KEY)
load_dotenv()

from adaptyv import FoundryClient, Lab  # noqa: E402
from adaptyv.types.generated import ExperimentSpec, ExperimentType  # noqa: E402

# Skip all tests if no API key
pytestmark = pytest.mark.skipif(
    not os.environ.get("ADAPTYV_API_KEY"), reason="ADAPTYV_API_KEY not set"
)


class TestFoundryClientIntegration:
    """Test FoundryClient against real API."""

    @pytest.fixture
    def client(self) -> FoundryClient:
        """Create real client."""
        return FoundryClient(api_key=os.environ["ADAPTYV_API_KEY"])

    def test_list_targets(self, client: FoundryClient) -> None:
        """Should list targets from catalog."""
        result = client.targets.list(page=1, per_page=10)

        print("\n=== Targets ===")
        print(f"Total: {result.total}")
        print(f"Page: {result.page}, Per page: {result.per_page}")
        print("First 5 targets:")
        for t in result.targets[:5]:
            print(f"  - {t.name} ({t.vendor_name}) - {t.catalog_number}")

        assert result.total > 0
        assert len(result.targets) > 0
        assert result.targets[0].id is not None
        assert result.targets[0].name is not None

    def test_search_targets(self, client: FoundryClient) -> None:
        """Should search targets by name."""
        result = client.targets.search("PD", limit=10)

        print("\n=== Target Search 'PD' ===")
        print(f"Found {len(result.targets)} targets")
        for t in result.targets[:5]:
            print(f"  - {t.id}: {t.name}")

    def test_get_target(self, client: FoundryClient) -> None:
        """Should get single target by ID."""
        target_id = "4e7659cd-2d6a-53b5-b3ee-93896a7589d6"
        result = client.targets.get(target_id)

        print("\n=== Target Details ===")
        print(f"ID: {result.id}")
        print(f"Name: {result.name}")
        print(f"Vendor: {result.vendor_name}")
        print(f"Catalog: {result.catalog_number}")

        assert result.id == target_id
        assert result.name is not None

    def test_list_experiments(self, client: FoundryClient) -> None:
        """Should list experiments (may be empty)."""
        result = client.experiments.list()

        print("\n=== Experiments List ===")
        print(f"Total: {len(result.experiments)} experiments")
        for exp in result.experiments[:3]:
            print(f"  - {exp.id}: {exp.name} ({exp.status})")

        # Just verify the structure is correct
        assert hasattr(result, "experiments")

    @pytest.mark.slow
    def test_create_experiment(self, client: FoundryClient) -> None:
        """Test experiment creation against real API.

        This test requires an API key with create_experiment permission.
        It will FAIL if the key lacks permissions - no silent passes.
        """
        # Get a valid target from catalog - API requires target_id even for thermostability
        # (API validation bug: docs say optional, code requires it)
        targets = client.targets.list(page=1, per_page=1)
        target_id = targets.targets[0].id if targets.targets else None

        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            target_id=target_id,
            sequences={"test_seq": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )

        result = client.experiments.create(
            name="SDK Integration Test",
            experiment_spec=spec,
        )

        print("\n=== Experiment Created ===")
        print(f"Experiment ID: {result.experiment_id}")

        assert result.experiment_id is not None
        assert result.experiment_id != ""


class TestLabIntegration:
    """Test Lab class against real API."""

    @pytest.fixture
    def lab(self) -> Lab:
        """Create real Lab instance."""
        return Lab.setup()

    def test_setup_from_env(self, lab: Lab) -> None:
        """Should set up from environment."""
        assert lab._settings.api_key is not None
        assert "foundry-api-public.adaptyvbio.com" in lab._settings.get_base_url()
        print("\n=== Lab Setup ===")
        print(f"Base URL: {lab._settings.get_base_url()}")

    def test_list_targets(self, lab: Lab) -> None:
        """Should list targets via Lab."""
        targets = lab.list_targets(per_page=5)

        print("\n=== Lab.list_targets() ===")
        print(f"Found {len(targets)} targets")
        for t in targets:
            print(f"  - {t['name']}")

        assert len(targets) > 0

    def test_search_targets(self, lab: Lab) -> None:
        """Should search targets."""
        targets = lab.search_targets("PD", limit=10)

        print("\n=== Lab.search_targets('PD') ===")
        print(f"Found {len(targets)} targets matching 'PD'")
        for t in targets:
            print(f"  - {t['name']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
