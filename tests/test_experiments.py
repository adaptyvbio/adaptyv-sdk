"""Comprehensive experiment type tests.

Tests all 5 experiment types with proper validation.
"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
from dotenv import load_dotenv

load_dotenv()

from adaptyv import FoundryClient
from adaptyv.client.foundry import get_client
from adaptyv.exceptions import APIError, ValidationError
from adaptyv.types.generated import ExperimentSpec, ExperimentType, Method

pytestmark = pytest.mark.skipif(
    not os.environ.get("ADAPTYV_API_KEY") or not os.environ.get("ADAPTYV_API_URL"),
    reason="ADAPTYV_API_KEY and ADAPTYV_API_URL must be set",
)


@pytest.fixture
def client() -> FoundryClient:
    return get_client()


@pytest.fixture
def target_id(client: FoundryClient) -> str:
    """Get first available target."""
    targets = client.targets.list(limit=1)
    return targets.targets[0].id


class TestAffinityExperiments:
    """Affinity experiments - require target + concentrations."""

    @pytest.mark.slow
    def test_affinity_bli_with_target(self, client: FoundryClient, target_id: str) -> None:
        """Create affinity BLI experiment with target from catalogue."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            method=Method.bli,
            target_id=target_id,
            sequences={"ab1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7],
            n_replicates=3,
        )
        result = client.experiments.create(
            name="SDK Test - Affinity BLI",
            experiment_spec=spec,
                    )
        assert result.experiment_id

    @pytest.mark.slow
    def test_affinity_spr_with_target(self, client: FoundryClient, target_id: str) -> None:
        """Create affinity SPR experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            method=Method.spr,
            target_id=target_id,
            sequences={"ab1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7],
            n_replicates=3,
        )
        result = client.experiments.create(
            name="SDK Test - Affinity SPR",
            experiment_spec=spec,
                    )
        assert result.experiment_id

    def test_affinity_requires_target(self, client: FoundryClient) -> None:
        """Affinity without target should fail validation."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            sequences={"ab1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7],
        )
        with pytest.raises(ValidationError, match="require target_id"):
            client.experiments.create(
                name="Should Fail",
                experiment_spec=spec,
                            )

    def test_affinity_requires_concentrations(self, client: FoundryClient, target_id: str) -> None:
        """Affinity without concentrations should fail validation."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            target_id=target_id,
            sequences={"ab1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
        )
        with pytest.raises(ValidationError, match="antigen_concentrations"):
            client.experiments.create(
                name="Should Fail",
                experiment_spec=spec,
                            )


class TestScreeningExperiments:
    """Screening experiments - require target."""

    @pytest.mark.slow
    def test_screening_bli(self, client: FoundryClient, target_id: str) -> None:
        """Create screening BLI experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            method=Method.bli,
            target_id=target_id,
            sequences={
                "clone_1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT",
                "clone_2": "EVQLVESGGGLVQPGGSLRLSCAASGFTFS",
            },
            n_replicates=2,
        )
        result = client.experiments.create(
            name="SDK Test - Screening BLI",
            experiment_spec=spec,
                    )
        assert result.experiment_id

    @pytest.mark.slow
    def test_screening_spr(self, client: FoundryClient, target_id: str) -> None:
        """Create screening SPR experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            method=Method.spr,
            target_id=target_id,
            sequences={"clone_1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
            n_replicates=2,
        )
        result = client.experiments.create(
            name="SDK Test - Screening SPR",
            experiment_spec=spec,
                    )
        assert result.experiment_id

    def test_screening_requires_target(self, client: FoundryClient) -> None:
        """Screening without target should fail validation."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            sequences={"clone_1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT"},
        )
        with pytest.raises(ValidationError, match="require target_id"):
            client.experiments.create(
                name="Should Fail",
                experiment_spec=spec,
                            )


class TestThermostabilityExperiments:
    """Thermostability - no target required."""

    @pytest.mark.slow
    def test_thermostability_no_target(self, client: FoundryClient) -> None:
        """Create thermostability without target."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=2,
        )
        result = client.experiments.create(
            name="SDK Test - Thermostability",
            experiment_spec=spec,
                    )
        assert result.experiment_id

    @pytest.mark.slow
    def test_thermostability_with_parameters(self, client: FoundryClient) -> None:
        """Thermostability with buffer parameters."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={"seq1": "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGD"},
            n_replicates=3,
            parameters={"buffer": "PBS", "ph": 7.4},
        )
        result = client.experiments.create(
            name="SDK Test - Thermostability PBS",
            experiment_spec=spec,
                    )
        assert result.experiment_id


class TestFluorescenceExperiments:
    """Fluorescence experiments - no target required."""

    @pytest.mark.slow
    def test_fluorescence(self, client: FoundryClient) -> None:
        """Create fluorescence experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.fluorescence,
            sequences={
                "variant_1": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT",
                "variant_2": "EVQLVESGGGLVQPGGSLRLSCAASGFTFS",
            },
            n_replicates=3,
        )
        result = client.experiments.create(
            name="SDK Test - Fluorescence",
            experiment_spec=spec,
                    )
        assert result.experiment_id


class TestExpressionExperiments:
    """Expression experiments - no target required."""

    @pytest.mark.slow
    def test_expression(self, client: FoundryClient) -> None:
        """Create expression experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.expression,
            sequences={
                "construct_A": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT",
                "construct_B": "EVQLVESGGGLVQPGGSLRLSCAASGFTFS",
            },
            n_replicates=2,
        )
        result = client.experiments.create(
            name="SDK Test - Expression",
            experiment_spec=spec,
                    )
        assert result.experiment_id


class TestSequenceMetadata:
    """Test sequence metadata fields."""

    @pytest.mark.slow
    def test_sequence_with_metadata(self, client: FoundryClient, target_id: str) -> None:
        """Create experiment with rich sequence metadata."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            target_id=target_id,
            sequences={
                "scfv_1": {
                    "aa_string": "QVQLVQSGAEVKKPGASVKVSCKASGYTFT",
                    "control": False,
                    "metadata": {
                        "type": "sc_fv",
                        "vh": "QVQLVQSGAEVKKPGAS",
                        "vl": "DIQMTQSPSSLSASVGD",
                        "linker": "GGGGSGGGGSGGGGS",
                        "tag_location": "C",
                    },
                },
            },
            n_replicates=2,
        )
        result = client.experiments.create(
            name="SDK Test - Metadata",
            experiment_spec=spec,
                    )
        assert result.experiment_id


class TestValidation:
    """Test client-side validation."""

    def test_empty_sequences_fails(self, client: FoundryClient) -> None:
        """Empty sequences should fail validation."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={},
        )
        with pytest.raises(ValidationError, match="at least one sequence"):
            client.experiments.create(
                name="Should Fail",
                experiment_spec=spec,
                            )

    def test_none_sequences_fails(self, client: FoundryClient) -> None:
        """None sequences should fail validation."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences=None,
        )
        with pytest.raises(ValidationError, match="at least one sequence"):
            client.experiments.create(
                name="Should Fail",
                experiment_spec=spec,
                            )

    def test_invalid_replicates(self, client: FoundryClient) -> None:
        """n_replicates < 1 should fail."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={"seq1": "MKTAYIAK"},
            n_replicates=0,
        )
        with pytest.raises(ValidationError, match="n_replicates"):
            client.experiments.create(
                name="Should Fail",
                experiment_spec=spec,
                            )


class TestCostEstimate:
    """Test cost estimation."""

    def test_cost_estimate_screening(self, client: FoundryClient, target_id: str) -> None:
        """Get cost estimate for screening experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.screening,
            target_id=target_id,
            sequences={
                "clone_1": "QVQLVQSGAEVKKPGAS",
                "clone_2": "EVQLVESGGGLVQPGGS",
            },
            n_replicates=2,
        )
        result = client.experiments.cost_estimate(spec)
        assert result is not None

    def test_cost_estimate_affinity(self, client: FoundryClient, target_id: str) -> None:
        """Get cost estimate for affinity experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.affinity,
            target_id=target_id,
            sequences={"ab1": "QVQLVQSGAEVKKPGAS"},
            antigen_concentrations=[1e-9, 1e-8, 1e-7],
            n_replicates=3,
        )
        result = client.experiments.cost_estimate(spec)
        assert result is not None

    def test_cost_estimate_thermostability(self, client: FoundryClient) -> None:
        """Get cost estimate for thermostability experiment."""
        spec = ExperimentSpec(
            experiment_type=ExperimentType.thermostability,
            sequences={"seq1": "QVQLVQSGAEVKKPGAS"},
            n_replicates=2,
        )
        result = client.experiments.cost_estimate(spec)
        assert result is not None


class TestExperimentsListFilters:
    """Test experiments.list() with filters."""

    def test_list_with_limit(self, client: FoundryClient) -> None:
        """Test listing with limit parameter."""
        result = client.experiments.list(limit=5)
        assert hasattr(result, "experiments")
        assert len(result.experiments) <= 5

    def test_list_with_search(self, client: FoundryClient) -> None:
        """Test listing with search filter."""
        result = client.experiments.list(search="SDK Test", limit=10)
        assert hasattr(result, "experiments")

    def test_list_with_status(self, client: FoundryClient) -> None:
        """Test listing with status filter."""
        result = client.experiments.list(status="done", limit=10)
        assert hasattr(result, "experiments")

    def test_list_with_multiple_statuses(self, client: FoundryClient) -> None:
        """Test listing with multiple status filters (comma-separated)."""
        result = client.experiments.list(status="done,in_production", limit=10)
        assert hasattr(result, "experiments")
