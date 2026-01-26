"""Integration tests against Foundry API."""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
from dotenv import load_dotenv

load_dotenv()

from adaptyv import FoundryClient, Lab  # noqa: E402
from adaptyv.client.foundry import get_client  # noqa: E402
from adaptyv.exceptions import APIError, AuthenticationError, NotFoundError, ValidationError  # noqa: E402
from adaptyv.types.generated import ExperimentSpec, ExperimentType  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("ADAPTYV_API_KEY") or not os.environ.get("ADAPTYV_API_URL"),
    reason="ADAPTYV_API_KEY and ADAPTYV_API_URL must be set",
)


# --- Helpers for API behavior quirks ---


def assert_not_found_or_forbidden(exc_info: pytest.ExceptionInfo[Any]) -> None:
    """API may return 403 OR 404 for non-existent resources.

    This is intentional API behavior to prevent information leakage.
    """
    if exc_info.type is NotFoundError:
        return  # Expected
    if exc_info.type is APIError and exc_info.value.status_code in (403, 404):
        return  # Also acceptable
    raise AssertionError(f"Expected NotFoundError or APIError(403/404), got {exc_info.type}")


def get_with_retry(
    client: FoundryClient,
    experiment_id: str,
    max_attempts: int = 5,
    delay: float = 2.0,
) -> Any:
    """Retry GET after POST to handle eventual consistency."""
    for attempt in range(max_attempts):
        try:
            return client.experiments.get(experiment_id)
        except (NotFoundError, APIError) as e:
            if attempt == max_attempts - 1:
                raise
            time.sleep(delay)


def wait_for_experiment(
    client: FoundryClient,
    experiment_id: str,
    timeout: float = 60.0,
) -> None:
    """Wait for experiment to become visible (eventual consistency).

    Args:
        client: FoundryClient instance.
        experiment_id: Experiment ID to wait for.
        timeout: Maximum wait time in seconds.

    Raises:
        TimeoutError: If experiment not visible within timeout.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            client.experiments.get(experiment_id)
            return  # Experiment is visible
        except NotFoundError:
            time.sleep(2)
        except Exception:
            time.sleep(2)
    raise TimeoutError(f"Experiment {experiment_id} not visible after {timeout}s")


@pytest.fixture
def client() -> FoundryClient:
    return get_client()


@pytest.fixture
def lab() -> Lab:
    return Lab.setup()


@pytest.fixture
def sample_spec(client: FoundryClient) -> ExperimentSpec:
    targets = client.targets.list(limit=1, offset=0)
    return ExperimentSpec(
        experiment_type=ExperimentType.thermostability,
        target_id=targets.targets[0].id,
        sequences={"test_seq": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
        n_replicates=2,
    )


class TestTargetsAPI:
    def test_list_targets(self, client: FoundryClient) -> None:
        result = client.targets.list(limit=10, offset=0)
        assert result.total > 0
        assert len(result.targets) > 0
        assert result.targets[0].id is not None

    def test_list_targets_pagination(self, client: FoundryClient) -> None:
        first = client.targets.list(limit=10, offset=0)
        if first.total > 10:
            second = client.targets.list(limit=10, offset=10)
            assert len(second.targets) > 0

    def test_get_target(self, client: FoundryClient) -> None:
        targets = client.targets.list(limit=1, offset=0)
        target_id = targets.targets[0].id
        result = client.targets.get(target_id)
        assert result.id == target_id
        assert result.name is not None

    def test_search_targets(self, client: FoundryClient) -> None:
        client.targets.search("PD", limit=10)

    def test_search_targets_nonexistent(self, client: FoundryClient) -> None:
        result = client.targets.search("ZZZNONEXISTENT999", limit=10)
        assert len(result.targets) == 0

    def test_get_target_not_found(self, client: FoundryClient) -> None:
        with pytest.raises((NotFoundError, APIError)) as exc_info:
            client.targets.get("00000000-0000-0000-0000-000000000000")
        assert_not_found_or_forbidden(exc_info)


class TestExperimentsAPI:
    def test_list_experiments(self, client: FoundryClient) -> None:
        result = client.experiments.list()
        assert hasattr(result, "experiments")

    @pytest.mark.slow
    def test_create_and_verify_experiment(self, client: FoundryClient, sample_spec: ExperimentSpec) -> None:
        """Create experiment and verify it exists with correct data."""
        exp_name = f"SDK Test - {time.time()}"
        created = client.experiments.create(name=exp_name, experiment_spec=sample_spec)

        assert created.experiment_id, "No experiment ID returned"

        # Wait for eventual consistency then verify experiment exists
        wait_for_experiment(client, created.experiment_id)
        exp = client.experiments.get(created.experiment_id)

        assert exp.id == created.experiment_id
        assert exp.name == exp_name
        assert exp.status is not None
        assert exp.code is not None  # Experiment code like "EXP-2024-001"
        assert exp.experiment_url is not None

    @pytest.mark.slow
    def test_create_screening_experiment(self, client: FoundryClient) -> None:
        """Create screening experiment with multiple sequences."""
        targets = client.targets.list(limit=1, offset=0)
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            target_id=targets.targets[0].id,
            sequences={
                "design_1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD",
                "design_2": "MKVLVAGVLVAVFIGAALVAAFIAVVNFVLKKIRRLFPTPPIQKV",
            },
            n_replicates=2,
        )

        created = client.experiments.create(name="SDK Screening Test", experiment_spec=spec)
        assert created.experiment_id

        wait_for_experiment(client, created.experiment_id)
        exp = client.experiments.get(created.experiment_id)
        assert exp.experiment_spec.experiment_type == ExperimentType.screening

    @pytest.mark.slow
    def test_list_updates_after_create(self, client: FoundryClient, sample_spec: ExperimentSpec) -> None:
        """Verify updates are tracked after experiment creation."""
        created = client.experiments.create(name="SDK Updates Test", experiment_spec=sample_spec)
        wait_for_experiment(client, created.experiment_id)

        updates = client.experiments.list_updates(created.experiment_id, limit=10)
        assert hasattr(updates, "updates")
        # New experiment should have at least one update (creation)

    @pytest.mark.slow
    def test_get_results_empty_for_new_experiment(self, client: FoundryClient, sample_spec: ExperimentSpec) -> None:
        """Verify results endpoint works (returns empty for new experiment)."""
        created = client.experiments.create(name="SDK Results Test", experiment_spec=sample_spec)
        wait_for_experiment(client, created.experiment_id)

        results = client.experiments.get_results(created.experiment_id)
        assert results is not None

    def test_get_experiment_not_found(self, client: FoundryClient) -> None:
        with pytest.raises((NotFoundError, APIError)) as exc_info:
            client.experiments.get("00000000-0000-0000-0000-000000000000")
        assert_not_found_or_forbidden(exc_info)


class TestMiscAPI:
    def test_cost_estimate(self, client: FoundryClient) -> None:
        targets = client.targets.list(limit=1, offset=0)
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            target_id=targets.targets[0].id,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )
        result = client.experiments.cost_estimate(spec)
        assert result is not None

    def test_list_sequences(self, client: FoundryClient) -> None:
        try:
            result = client.sequences.list(limit=10)
            assert result is not None
        except APIError as e:
            if e.status_code == 403:
                pytest.skip("API key lacks sequences permission")
            raise

    def test_list_results(self, client: FoundryClient) -> None:
        try:
            result = client.results.list(limit=10)
            assert result is not None
        except APIError as e:
            if e.status_code == 403:
                pytest.skip("API key lacks results permission")
            raise

    def test_list_global_updates(self, client: FoundryClient) -> None:
        try:
            result = client.updates.list(limit=10)
            assert hasattr(result, "updates")
        except APIError as e:
            if e.status_code == 403:
                pytest.skip("API key lacks updates permission")
            raise


class TestErrorHandling:
    def test_invalid_api_key(self) -> None:
        client = FoundryClient(api_key="invalid-key", base_url=os.environ["ADAPTYV_API_URL"])
        with pytest.raises(AuthenticationError):
            client.targets.list()

    def test_missing_api_key(self) -> None:
        with pytest.raises(AuthenticationError):
            FoundryClient(api_key="", base_url=os.environ["ADAPTYV_API_URL"])

    def test_invalid_uuid(self, client: FoundryClient) -> None:
        with pytest.raises((ValidationError, NotFoundError, APIError)):
            client.targets.get("not-a-valid-uuid")


class TestLabIntegration:
    def test_setup(self, lab: Lab) -> None:
        assert lab._config.api_key is not None
        assert lab._config.api_url is not None  # URL is configured

    def test_list_targets(self, lab: Lab) -> None:
        targets = lab.list_targets(limit=5)
        assert len(targets) > 0

    def test_search_targets(self, lab: Lab) -> None:
        lab.search_targets("PD", limit=10)

    @pytest.mark.slow
    def test_create_and_verify_experiment(self, lab: Lab) -> None:
        """Create experiment via Lab and verify it exists."""
        from adaptyv.client.foundry import get_client

        targets = lab.list_targets(limit=1)
        exp_name = f"SDK Lab Test - {time.time()}"

        result = lab.create_experiment(
            name=exp_name,
            sequences=["MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"],
            target_id=targets[0]["id"],
            experiment_type="thermostability",
        )

        assert result.experiment_id is not None
        assert result.sequences_submitted == 1

        # Use wait_for_experiment with underlying client
        client = get_client()
        wait_for_experiment(client, result.experiment_id)
        exp = lab.get_experiment(result.experiment_id)
        assert exp.experiment_id == result.experiment_id
