"""Comprehensive API coverage tests for Foundry API.

This module tests all API endpoints with real API calls.
Tests are marked with @pytest.mark.slow for tests that create experiments
(costly operations) or @pytest.mark.integration for read-only API tests.
"""

from __future__ import annotations

import functools
import time
from typing import TYPE_CHECKING, TypeVar

import pytest
import respx
from httpx import Response

if TYPE_CHECKING:
    from adaptyv.client.foundry import FoundryClient

from adaptyv.client.foundry import FoundryClient as FC
from adaptyv.exceptions import APIError, NotFoundError
from adaptyv.types.generated import (
    ExperimentSpec,
    ExperimentStatus,
    ExperimentType,
    ExpInfo,
    ResultsStatus,
)

F = TypeVar("F")


def skip_on_backend_error(func: F) -> F:
    """Skip test if backend returns 5xx error."""

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if e.status_code >= 500:
                pytest.skip(f"Backend error: {e}")
            raise

    return wrapper  # type: ignore[return-value]


def wait_for_experiment(client: FC, experiment_id: str, timeout: float = 30.0) -> None:
    """Wait for experiment to become visible (eventual consistency)."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            client.experiments.get(experiment_id)
            return
        except NotFoundError:
            time.sleep(2)
    raise TimeoutError(f"Experiment {experiment_id} not visible after {timeout}s")


# --- Test Fixtures ---


@pytest.fixture
def thermostability_spec() -> ExperimentSpec:
    """Thermostability spec (no target_id required)."""
    return ExperimentSpec(
        experiment_type=ExperimentType.thermostability,
        sequences={"test_seq": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
        n_replicates=2,
    )


# --- Unit Tests (Mocked) ---


class TestOrganizationIdBugFix:
    """Verify organization_id is properly passed to API."""

    @respx.mock
    def test_organization_id_included_in_payload(self) -> None:
        """organization_id should be included in create request payload."""
        client = FC(api_key="test-key", base_url="https://api.test.com")

        route = respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        client.experiments.create(
            name="Test",
            experiment_spec={
                "experiment_type": "thermostability",
                "sequences": {"seq1": "MVKVGVNG"},
            },
            organization_id="org-12345",
        )

        request_body = route.calls[0].request.content.decode()
        assert "org-12345" in request_body
        assert "organization_id" in request_body

    @respx.mock
    def test_organization_id_not_included_when_none(self) -> None:
        """organization_id should not be in payload when not provided."""
        client = FC(api_key="test-key", base_url="https://api.test.com")

        route = respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        client.experiments.create(
            name="Test",
            experiment_spec={
                "experiment_type": "thermostability",
                "sequences": {"seq1": "MVKVGVNG"},
            },
        )

        request_body = route.calls[0].request.content.decode()
        assert "organization_id" not in request_body


class TestAutoconfirmParameter:
    """Verify confirmed=True parameter works correctly."""

    @respx.mock
    def test_confirmed_true_in_payload(self) -> None:
        """confirmed=True should send skip_draft=True in request payload."""
        client = FC(api_key="test-key", base_url="https://api.test.com")

        route = respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        client.experiments.create(
            name="Test",
            experiment_spec={
                "experiment_type": "thermostability",
                "sequences": {"seq1": "MVKVGVNG"},
            },
            confirmed=True,
        )

        request_body = route.calls[0].request.content.decode()
        # API expects skip_draft instead of confirmed
        assert '"skip_draft": true' in request_body or '"skip_draft":true' in request_body


class TestAutoLinkMaterialParameter:
    """Verify auto_link_material parameter works correctly."""

    @respx.mock
    def test_auto_link_material_in_payload(self) -> None:
        """auto_link_material=True should be included in request payload."""
        client = FC(api_key="test-key", base_url="https://api.test.com")

        route = respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        client.experiments.create(
            name="Test",
            experiment_spec={
                "experiment_type": "thermostability",
                "sequences": {"seq1": "MVKVGVNG"},
            },
            auto_link_material=True,
        )

        request_body = route.calls[0].request.content.decode()
        assert "auto_link_material" in request_body


# --- Integration Tests (Read-only, any API key) ---


@pytest.mark.integration
class TestTargetsAPIIntegration:
    """Target API read tests (work with any API key)."""

    def test_list_targets(self, ada_client: FoundryClient) -> None:
        """List targets returns results."""
        result = ada_client.targets.list(limit=10)
        assert result.total > 0
        assert len(result.items) > 0

    def test_get_target(self, ada_client: FoundryClient) -> None:
        """Get specific target by ID."""
        targets = ada_client.targets.list(limit=1)
        target_id = targets.items[0].id

        result = ada_client.targets.get(target_id)
        assert result.id == target_id
        assert result.name is not None

    def test_search_targets_pdl1(self, ada_client: FoundryClient) -> None:
        """Search for PD-L1 targets."""
        result = ada_client.targets.search("PD-L1", limit=10)
        # May or may not find results depending on catalog
        assert hasattr(result, "items")

    def test_search_targets_empty(self, ada_client: FoundryClient) -> None:
        """Search for non-existent target returns empty."""
        result = ada_client.targets.search("ZZZNONEXISTENT999", limit=10)
        assert len(result.items) == 0


@pytest.mark.integration
class TestExperimentsAPIReadIntegration:
    """Experiments API read tests (work with any API key)."""

    @skip_on_backend_error
    def test_list_experiments(self, ada_client: FoundryClient) -> None:
        """List experiments returns results."""
        result = ada_client.experiments.list(limit=10)
        assert hasattr(result, "items")

    @skip_on_backend_error
    def test_list_experiments_with_filters(self, ada_client: FoundryClient) -> None:
        """List experiments with status filter."""
        result = ada_client.experiments.list(
            limit=10,
            filter="eq(status,done)",
        )
        assert hasattr(result, "items")

    @skip_on_backend_error
    def test_cost_estimate(self, ada_client: FoundryClient) -> None:
        """Cost estimate endpoint works."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )
        result = ada_client.experiments.cost_estimate(spec)
        assert result is not None


@pytest.mark.integration
class TestGlobalUpdatesAPI:
    """Global updates API tests."""

    def test_list_global_updates(self, ada_client: FoundryClient) -> None:
        """List global updates feed."""
        try:
            result = ada_client.updates.list(limit=10)
            assert hasattr(result, "items")
        except APIError as e:
            if e.status_code == 403:
                pytest.skip("API key lacks updates permission")
            raise


@pytest.mark.integration
class TestSequencesAPIIntegration:
    """Sequences API integration tests."""

    @skip_on_backend_error
    def test_list_sequences(self, ada_client: FoundryClient) -> None:
        """List sequences returns results."""
        result = ada_client.sequences.list(limit=10)
        assert hasattr(result, "items")
        assert hasattr(result, "total")

    @skip_on_backend_error
    def test_list_sequences_with_search(self, ada_client: FoundryClient) -> None:
        """Search sequences by name."""
        result = ada_client.sequences.list(search="design", limit=10)
        assert hasattr(result, "items")

    @skip_on_backend_error
    def test_get_sequence(self, ada_client: FoundryClient) -> None:
        """Get sequence by ID."""
        sequences = ada_client.sequences.list(limit=1)
        if not sequences.items:
            pytest.skip("No sequences available")

        seq_id = sequences.items[0].id
        result = ada_client.sequences.get(seq_id)
        assert result.id == seq_id


@pytest.mark.integration
class TestResultsAPIIntegration:
    """Results API integration tests."""

    @skip_on_backend_error
    def test_list_results(self, ada_client: FoundryClient) -> None:
        """List results returns structure."""
        result = ada_client.results.list(limit=10)
        assert hasattr(result, "items")
        assert hasattr(result, "total")

    @skip_on_backend_error
    def test_get_result(self, ada_client: FoundryClient) -> None:
        """Get result by ID if available."""
        results = ada_client.results.list(limit=1)
        if not results.items:
            pytest.skip("No results available")

        result_id = results.items[0].id
        result = ada_client.results.get(result_id)
        assert result.id == result_id

    @skip_on_backend_error
    def test_get_experiment_results(self, ada_client: FoundryClient) -> None:
        """Get results for a specific experiment."""
        # Find an experiment with results (filter by results_status, not status)
        experiments = ada_client.experiments.list(limit=50)
        with_results = [e for e in experiments.items if e.results_status != ResultsStatus.none]

        if not with_results:
            pytest.skip("No experiments with results available")

        for exp in with_results:
            try:
                result = ada_client.experiments.get_results(exp.id, limit=5)
                assert hasattr(result, "items")
                return
            except NotFoundError:
                continue

        pytest.skip("No experiments with accessible results found")


# --- Submission Tests (ADA org key required) ---


@pytest.mark.slow
class TestSubmissions:
    """Experiment submission tests using ADA org key."""

    def test_create_thermostability(
        self, ada_client: FoundryClient, thermostability_spec: ExperimentSpec
    ) -> None:
        """Create thermostability experiment (no target required)."""
        result = ada_client.experiments.create(
            name=f"API Coverage Test - Thermo - {time.time()}",
            experiment_spec=thermostability_spec,
        )
        assert result.experiment_id
        assert len(result.experiment_id) > 0

    def test_create_screening_with_target(self, ada_client: FoundryClient) -> None:
        """Create screening experiment with target_id."""
        # Get first target
        targets = ada_client.targets.list(limit=1)
        if not targets.items:
            pytest.skip("No targets available")

        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            target_id=targets.items[0].id,
            sequences={
                "design_1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD",
                "design_2": "MKVLVAGVLVAVFIGAALVAAFIAVVNFVLKKIRRLFPTPPIQKV",
            },
            n_replicates=2,
        )

        result = ada_client.experiments.create(
            name=f"API Coverage Test - Screening - {time.time()}",
            experiment_spec=spec,
        )
        assert result.experiment_id

    def test_create_affinity_with_target(self, ada_client: FoundryClient) -> None:
        """Create affinity experiment with target_id."""
        targets = ada_client.targets.list(limit=1)
        if not targets.items:
            pytest.skip("No targets available")

        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            target_id=targets.items[0].id,
            sequences={"ab1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7],
            n_replicates=2,
        )

        result = ada_client.experiments.create(
            name=f"API Coverage Test - Affinity - {time.time()}",
            experiment_spec=spec,
        )
        assert result.experiment_id

    def test_create_expression(self, ada_client: FoundryClient) -> None:
        """Create expression experiment (no target required)."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.expression,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )

        result = ada_client.experiments.create(
            name=f"API Coverage Test - Expression - {time.time()}",
            experiment_spec=spec,
        )
        assert result.experiment_id

    def test_create_fluorescence(self, ada_client: FoundryClient) -> None:
        """Create fluorescence experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.fluorescence,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )

        result = ada_client.experiments.create(
            name=f"API Coverage Test - Fluorescence - {time.time()}",
            experiment_spec=spec,
        )
        assert result.experiment_id

    def test_create_with_auto_link_material(
        self, ada_client: FoundryClient, thermostability_spec: ExperimentSpec
    ) -> None:
        """Create experiment with auto_link_material=True."""
        result = ada_client.experiments.create(
            name=f"API Coverage Test - AutoLink - {time.time()}",
            experiment_spec=thermostability_spec,
            auto_link_material=True,
        )
        assert result.experiment_id

    def test_get_experiment_after_create(
        self, ada_client: FoundryClient, thermostability_spec: ExperimentSpec
    ) -> None:
        """Verify experiment details after creation."""
        exp_name = f"API Coverage Test - Verify - {time.time()}"
        created = ada_client.experiments.create(
            name=exp_name,
            experiment_spec=thermostability_spec,
        )

        # Wait for experiment to be visible (eventual consistency)
        wait_for_experiment(ada_client, created.experiment_id, timeout=30.0)

        exp = ada_client.experiments.get(created.experiment_id)
        assert exp.id == created.experiment_id
        assert exp.name == exp_name
        assert exp.status is not None
        assert exp.code is not None

    def test_get_quote_after_create(
        self, ada_client: FoundryClient, thermostability_spec: ExperimentSpec
    ) -> None:
        """Get quote for newly created experiment."""
        created = ada_client.experiments.create(
            name=f"API Coverage Test - Quote - {time.time()}",
            experiment_spec=thermostability_spec,
        )

        time.sleep(2)

        try:
            quote = ada_client.experiments.get_quote(created.experiment_id)
            assert quote.experiment_id == created.experiment_id
        except (NotFoundError, APIError) as e:
            # Quote may not be generated yet (404) or permission denied (403)
            if isinstance(e, NotFoundError) or (
                isinstance(e, APIError) and e.status_code in (403, 404)
            ):
                pytest.skip("Quote not available yet or no permission")
            raise

    def test_list_updates_after_create(
        self, ada_client: FoundryClient, thermostability_spec: ExperimentSpec
    ) -> None:
        """List updates for newly created experiment."""
        created = ada_client.experiments.create(
            name=f"API Coverage Test - Updates - {time.time()}",
            experiment_spec=thermostability_spec,
        )

        time.sleep(2)

        try:
            updates = ada_client.experiments.list_updates(created.experiment_id, limit=10)
            assert hasattr(updates, "updates")
        except APIError as e:
            if e.status_code == 403:
                pytest.skip("API key lacks updates permission")
            raise


@pytest.mark.slow
class TestAutoconfirm:
    """Test autoconfirm (confirmed=True) functionality."""

    @skip_on_backend_error
    def test_autoconfirm_creates_non_draft(
        self, ada_client: FoundryClient, thermostability_spec: ExperimentSpec
    ) -> None:
        """confirmed=True should skip draft status."""
        result = ada_client.experiments.create(
            name=f"SDK Test - Autoconfirm - {time.time()}",
            experiment_spec=thermostability_spec,
            confirmed=True,
        )

        # Wait with retry logic (30 attempts * 2s = 60s max)
        exp = None
        for _attempt in range(30):
            try:
                exp = ada_client.experiments.get(result.experiment_id)
                break
            except NotFoundError:
                time.sleep(2)

        assert exp is not None, f"Experiment {result.experiment_id} not visible after 60s"

        # With autoconfirm, status should not be draft
        assert exp.status != ExperimentStatus.draft
        assert exp.status != ExperimentStatus.waiting_for_confirmation

    @skip_on_backend_error
    def test_draft_without_autoconfirm(
        self, ada_client: FoundryClient, thermostability_spec: ExperimentSpec
    ) -> None:
        """Without confirmed=True, experiment should be in draft."""
        result = ada_client.experiments.create(
            name=f"SDK Test - Draft - {time.time()}",
            experiment_spec=thermostability_spec,
            confirmed=False,  # Explicit draft
        )

        # Wait for visibility (30 attempts * 2s = 60s max)
        exp = None
        for _attempt in range(30):
            try:
                exp = ada_client.experiments.get(result.experiment_id)
                break
            except NotFoundError:
                time.sleep(2)

        assert exp is not None, f"Experiment {result.experiment_id} not visible after 60s"

        # Without autoconfirm, should be draft or waiting_for_confirmation
        assert exp.status in (ExperimentStatus.draft, ExperimentStatus.waiting_for_confirmation)


@pytest.mark.slow
class TestAllExperimentTypesAutoconfirm:
    """Test all experiment types with autoconfirm (confirmed=True)."""

    def _wait_and_get(
        self, client: FoundryClient, exp_id: str, timeout: int = 30
    ) -> ExpInfo | None:
        """Wait for experiment visibility with retry."""
        for _ in range(timeout // 2):
            try:
                return client.experiments.get(exp_id)
            except NotFoundError:
                time.sleep(2)
        return None

    @skip_on_backend_error
    def test_thermostability_autoconfirm(self, ada_client: FoundryClient) -> None:
        """Thermostability with autoconfirm."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )
        result = ada_client.experiments.create(
            name=f"SDK Test - Thermo Autoconfirm - {time.time()}",
            experiment_spec=spec,
            confirmed=True,
        )
        assert result.experiment_id

        # Verify not in draft status
        exp = self._wait_and_get(ada_client, result.experiment_id)
        if exp:
            assert exp.status not in (
                ExperimentStatus.draft,
                ExperimentStatus.waiting_for_confirmation,
            )

    @skip_on_backend_error
    def test_expression_autoconfirm(self, ada_client: FoundryClient) -> None:
        """Expression with autoconfirm."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.expression,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )
        result = ada_client.experiments.create(
            name=f"SDK Test - Expression Autoconfirm - {time.time()}",
            experiment_spec=spec,
            confirmed=True,
        )
        assert result.experiment_id

        # Verify not in draft status
        exp = self._wait_and_get(ada_client, result.experiment_id)
        if exp:
            assert exp.status not in (
                ExperimentStatus.draft,
                ExperimentStatus.waiting_for_confirmation,
            )

    @skip_on_backend_error
    def test_fluorescence_autoconfirm(self, ada_client: FoundryClient) -> None:
        """Fluorescence with autoconfirm."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.fluorescence,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )
        result = ada_client.experiments.create(
            name=f"SDK Test - Fluorescence Autoconfirm - {time.time()}",
            experiment_spec=spec,
            confirmed=True,
        )
        assert result.experiment_id

        # Verify not in draft status
        exp = self._wait_and_get(ada_client, result.experiment_id)
        if exp:
            assert exp.status not in (
                ExperimentStatus.draft,
                ExperimentStatus.waiting_for_confirmation,
            )

    @skip_on_backend_error
    def test_screening_with_target_autoconfirm(self, ada_client: FoundryClient) -> None:
        """Screening with real target_id and autoconfirm."""
        targets = ada_client.targets.list(limit=1)
        if not targets.items:
            pytest.skip("No targets available")

        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            target_id=targets.items[0].id,
            sequences={
                "design_1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD",
                "design_2": "MKVLVAGVLVAVFIGAALVAAFIAVVNFVLKKIRRLFPTPPIQKV",
            },
            n_replicates=2,
        )
        result = ada_client.experiments.create(
            name=f"SDK Test - Screening Autoconfirm - {time.time()}",
            experiment_spec=spec,
            confirmed=True,
        )
        assert result.experiment_id

        # Verify not in draft status
        exp = self._wait_and_get(ada_client, result.experiment_id)
        if exp:
            assert exp.status not in (
                ExperimentStatus.draft,
                ExperimentStatus.waiting_for_confirmation,
            )

    @skip_on_backend_error
    def test_affinity_with_target_autoconfirm(self, ada_client: FoundryClient) -> None:
        """Affinity with real target_id and autoconfirm."""
        targets = ada_client.targets.list(limit=1)
        if not targets.items:
            pytest.skip("No targets available")

        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            target_id=targets.items[0].id,
            sequences={"ab1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7],
            n_replicates=2,
        )
        result = ada_client.experiments.create(
            name=f"SDK Test - Affinity Autoconfirm - {time.time()}",
            experiment_spec=spec,
            confirmed=True,
        )
        assert result.experiment_id

        # Verify not in draft status
        exp = self._wait_and_get(ada_client, result.experiment_id)
        if exp:
            assert exp.status not in (
                ExperimentStatus.draft,
                ExperimentStatus.waiting_for_confirmation,
            )


@pytest.mark.slow
class TestPricingCalculator:
    """Test pricing calculator (cost_estimate) endpoint."""

    def test_cost_estimate_thermostability(self, ada_client: FoundryClient) -> None:
        """Cost estimate for thermostability."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )
        result = ada_client.experiments.cost_estimate(spec)
        assert result is not None

    def test_cost_estimate_screening_with_target(self, ada_client: FoundryClient) -> None:
        """Cost estimate for screening with target."""
        targets = ada_client.targets.list(limit=1)
        if not targets.items:
            pytest.skip("No targets available")

        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            target_id=targets.items[0].id,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )
        result = ada_client.experiments.cost_estimate(spec)
        assert result is not None

    def test_cost_estimate_affinity_multiple_concentrations(
        self, ada_client: FoundryClient
    ) -> None:
        """Cost estimate for affinity with multiple concentrations."""
        targets = ada_client.targets.list(limit=1)
        if not targets.items:
            pytest.skip("No targets available")

        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            target_id=targets.items[0].id,
            sequences={"ab1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7, 1e-6, 1e-5],
            n_replicates=3,
        )
        result = ada_client.experiments.cost_estimate(spec)
        assert result is not None
