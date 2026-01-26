"""Full experiment workflow tests - creates AND confirms experiments.

WARNING: These tests incur real costs. Only run against ADA org.
Run with: pytest tests/test_full_workflow.py -v -s -m costly
"""

from __future__ import annotations

import os
import time

import pytest
from dotenv import load_dotenv

load_dotenv()

from adaptyv import FoundryClient
from adaptyv.client.foundry import get_client
from adaptyv.exceptions import APIError, NotFoundError
from adaptyv.types.generated import (
    ExperimentSpec,
    ExperimentStatus,
    ExperimentType,
    Method,
)

pytestmark = [
    pytest.mark.skipif(
        not os.environ.get("ADAPTYV_API_KEY") or not os.environ.get("ADAPTYV_API_URL"),
        reason="ADAPTYV_API_KEY and ADAPTYV_API_URL must be set",
    ),
    pytest.mark.costly,  # All tests in this file are costly
]


@pytest.fixture
def client() -> FoundryClient:
    return get_client()


@pytest.fixture
def target_id(client: FoundryClient) -> str:
    """Get first available target."""
    targets = client.targets.list(limit=1)
    return targets.targets[0].id


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
        except Exception as e:
            # Log other errors but keep trying
            print(f"Unexpected error waiting for experiment: {e}")
            time.sleep(2)
    raise TimeoutError(f"Experiment {experiment_id} not visible after {timeout}s")


def wait_for_quote(
    client: FoundryClient,
    experiment_id: str,
    timeout: float = 60.0,
) -> dict:
    """Poll until quote is ready.

    Args:
        client: FoundryClient instance.
        experiment_id: Experiment to poll.
        timeout: Maximum wait time in seconds.

    Returns:
        Quote response when ready.

    Raises:
        TimeoutError: If quote not ready within timeout.
    """
    # First wait for experiment to be visible
    wait_for_experiment(client, experiment_id, timeout=timeout / 2)

    start = time.time()
    while time.time() - start < timeout:
        try:
            quote = client.experiments.get_quote(experiment_id)
            if quote.amount_total > 0:
                return quote
        except NotFoundError:
            pass  # Experiment not yet visible, keep waiting
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Quote not ready after {timeout}s")


class TestAffinityWorkflow:
    """Full affinity experiment workflow with BLI and SPR."""

    def test_affinity_bli_full_workflow(self, client: FoundryClient, target_id: str) -> None:
        """Create, quote, and confirm BLI affinity experiment."""
        # 1. Create experiment
        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            method=Method.bli,
            target_id=target_id,
            sequences={"test_ab": "QVQLVQSGAEVKKPGASVKVSCKASGYTFTNYDIN"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7],
            n_replicates=3,
        )
        created = client.experiments.create(
            name="SDK Full Test - Affinity BLI",
            experiment_spec=spec,
                    )
        assert created.experiment_id
        print(f"Created experiment: {created.experiment_id}")

        # 2. Wait for Stripe quote
        quote = wait_for_quote(client, created.experiment_id)
        print(f"Quote ready: {quote.amount_total} {quote.currency}")
        assert quote.amount_total > 0

        # 3. Confirm experiment
        confirmed = client.experiments.confirm(created.experiment_id)
        assert confirmed.status == "confirmed"
        print(f"Confirmed at: {confirmed.confirmed_at}")

        # 4. Verify status changed
        exp = client.experiments.get(created.experiment_id)
        assert exp.status != ExperimentStatus.waiting_for_confirmation
        print(f"Final status: {exp.status}")

    def test_affinity_spr_full_workflow(self, client: FoundryClient, target_id: str) -> None:
        """Create, quote, and confirm SPR affinity experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            method=Method.spr,
            target_id=target_id,
            sequences={"test_ab": "QVQLVQSGAEVKKPGASVKVSCKASGYTFTNYDIN"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7],
            n_replicates=3,
        )
        created = client.experiments.create(
            name="SDK Full Test - Affinity SPR",
            experiment_spec=spec,
                    )
        quote = wait_for_quote(client, created.experiment_id)
        confirmed = client.experiments.confirm(created.experiment_id)
        assert confirmed.status == "confirmed"


class TestScreeningWorkflow:
    """Full screening workflow with BLI and SPR."""

    def test_screening_bli_full_workflow(self, client: FoundryClient, target_id: str) -> None:
        """Create and confirm BLI screening experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            method=Method.bli,
            target_id=target_id,
            sequences={
                "clone_1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT",
                "clone_2": "EVQLVESGGGLVQPGGSLRLSCAASGFTFS",
                "clone_3": "QVQLQQSGPGLVKPSQTLSLTCAISGDSVS",
            },
            n_replicates=2,
        )
        created = client.experiments.create(
            name="SDK Full Test - Screening BLI",
            experiment_spec=spec,
                    )
        quote = wait_for_quote(client, created.experiment_id)
        confirmed = client.experiments.confirm(created.experiment_id)
        assert confirmed.status == "confirmed"

    def test_screening_spr_full_workflow(self, client: FoundryClient, target_id: str) -> None:
        """Create and confirm SPR screening experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            method=Method.spr,
            target_id=target_id,
            sequences={"clone_1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            n_replicates=2,
        )
        created = client.experiments.create(
            name="SDK Full Test - Screening SPR",
            experiment_spec=spec,
                    )
        quote = wait_for_quote(client, created.experiment_id)
        confirmed = client.experiments.confirm(created.experiment_id)
        assert confirmed.status == "confirmed"


class TestThermostabilityWorkflow:
    """Full thermostability workflow."""

    def test_thermostability_full_workflow(self, client: FoundryClient) -> None:
        """Create and confirm thermostability (no target needed)."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={
                "candidate_1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFTNYDIN",
                "candidate_2": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMN",
            },
            n_replicates=3,
            parameters={"buffer": "PBS", "ph": 7.4},
        )
        created = client.experiments.create(
            name="SDK Full Test - Thermostability",
            experiment_spec=spec,
                    )
        quote = wait_for_quote(client, created.experiment_id)
        confirmed = client.experiments.confirm(created.experiment_id)
        assert confirmed.status == "confirmed"


class TestFluorescenceWorkflow:
    """Full fluorescence workflow."""

    def test_fluorescence_full_workflow(self, client: FoundryClient) -> None:
        """Create and confirm fluorescence experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.fluorescence,
            sequences={
                "variant_1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFTNYDIN",
                "variant_2": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMN",
            },
            n_replicates=3,
        )
        created = client.experiments.create(
            name="SDK Full Test - Fluorescence",
            experiment_spec=spec,
                    )
        quote = wait_for_quote(client, created.experiment_id)
        confirmed = client.experiments.confirm(created.experiment_id)
        assert confirmed.status == "confirmed"


class TestExpressionWorkflow:
    """Full expression workflow."""

    def test_expression_full_workflow(self, client: FoundryClient) -> None:
        """Create and confirm expression experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.expression,
            sequences={
                "construct_A": "QVQLVQSGAEVKKPGASVKVSCKASGYTFTNYDIN",
                "construct_B": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMN",
            },
            n_replicates=2,
        )
        created = client.experiments.create(
            name="SDK Full Test - Expression",
            experiment_spec=spec,
                    )
        quote = wait_for_quote(client, created.experiment_id)
        confirmed = client.experiments.confirm(created.experiment_id)
        assert confirmed.status == "confirmed"


class TestConfirmedFlagWorkflow:
    """Test creating experiment with confirmed=True (skip draft)."""

    def test_create_with_confirmed_true(self, client: FoundryClient) -> None:
        """Create experiment directly in confirmed state."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={"seq1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFTNYDIN"},
            n_replicates=2,
        )
        created = client.experiments.create(
            name="SDK Test - Direct Confirm",
            experiment_spec=spec,
            confirmed=True,  # Skip draft!
        )
        assert created.experiment_id

        # Wait for experiment to be visible (eventual consistency)
        wait_for_experiment(client, created.experiment_id)
        exp = client.experiments.get(created.experiment_id)
        # When confirmed=True, experiment should skip draft state
        assert exp.status != ExperimentStatus.draft
        print(f"Status after confirmed=True: {exp.status}")
