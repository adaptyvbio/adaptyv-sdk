"""Tests for BindCraft workflow adapter."""

from unittest.mock import MagicMock, patch

import pytest

from adaptyv.workflows.bindcraft import (
    BindCraftConfig,
    BindCraftDesign,
    BindCraftRun,
    BindCraftWorkflow,
)


class TestBindCraftDesign:
    """Tests for BindCraftDesign dataclass."""

    def test_design_creation(self):
        """Should create a design with required fields."""
        design = BindCraftDesign(
            design_id="0001",
            sequence="MVKVGVNG",
        )
        assert design.design_id == "0001"
        assert design.sequence == "MVKVGVNG"
        assert design.status == "pending"

    def test_design_with_metrics(self):
        """Should store metrics."""
        design = BindCraftDesign(
            design_id="0001",
            sequence="MVKVGVNG",
            metrics={"plddt": 85.2, "iptm": 0.78},
            status="completed",
        )
        assert design.metrics["plddt"] == 85.2
        assert design.status == "completed"

    def test_design_to_dict(self):
        """Should convert to dict."""
        design = BindCraftDesign(
            design_id="0001",
            sequence="MVKVGVNG",
            structure_path="/path/to/structure.pdb",
        )
        d = design.to_dict()
        assert d["design_id"] == "0001"
        assert d["sequence"] == "MVKVGVNG"
        assert d["structure_path"] == "/path/to/structure.pdb"


class TestBindCraftRun:
    """Tests for BindCraftRun dataclass."""

    def test_run_creation(self):
        """Should create a run with required fields."""
        run = BindCraftRun(
            run_id="abc123",
            output_path="/output/abc123",
        )
        assert run.run_id == "abc123"
        assert run.output_path == "/output/abc123"
        assert run.output_volume == "mosaic-bindcraft-out"

    def test_get_status_includes_error_and_resume_hint(self):
        """Should pass through error and resume_hint fields from status.json."""
        run = BindCraftRun(
            run_id="test123",
            output_path="/output/test123",
        )

        mock_vol = MagicMock()
        mock_vol.read_file.return_value = iter(
            [
                b"""{
                "run_id": "test123",
                "status": "failed",
                "error": {
                    "code": "bindcraft_failed",
                    "message": "Trajectory failed",
                    "stage": "trajectory",
                    "retryable": false
                },
                "resume_hint": {
                    "stage": "trajectory",
                    "message": "Resume at trajectory",
                    "retryable": false
                }
            }"""
            ]
        )

        with patch("modal.Volume.from_name", return_value=mock_vol):
            status = run.get_status()

        assert status["status"] == "failed"
        assert status["error"]["code"] == "bindcraft_failed"
        assert status["error"]["stage"] == "trajectory"
        assert status["resume_hint"]["stage"] == "trajectory"


class TestBindCraftConfig:
    """Tests for BindCraftConfig dataclass."""

    def test_default_config(self):
        """Should have sensible defaults."""
        config = BindCraftConfig()
        assert config.n_trajectories == 50
        assert config.binder_lengths == [80]
        assert config.number_of_final_designs == 50
        assert config.binder_chain == "B"
        assert config.target_chain == "A"
        assert config.runtime_seed is None

    def test_custom_config(self):
        """Should accept custom values."""
        config = BindCraftConfig(
            n_trajectories=100,
            binder_lengths=[70, 90, 110],
            number_of_final_designs=20,
        )
        assert config.n_trajectories == 100
        assert config.binder_lengths == [70, 90, 110]
        assert config.number_of_final_designs == 20

    def test_validation_n_trajectories(self):
        """Should reject invalid n_trajectories."""
        with pytest.raises(ValueError, match="n_trajectories must be >= 1"):
            BindCraftConfig(n_trajectories=0)

    def test_validation_binder_lengths(self):
        """Should reject empty binder_lengths."""
        with pytest.raises(ValueError, match="binder_lengths cannot be empty"):
            BindCraftConfig(binder_lengths=[])

    def test_validation_number_of_final_designs(self):
        """Should reject invalid number_of_final_designs."""
        with pytest.raises(ValueError, match="number_of_final_designs must be >= 1"):
            BindCraftConfig(number_of_final_designs=0)


class TestBindCraftWorkflow:
    """Tests for BindCraftWorkflow class."""

    def test_init_with_default_config(self):
        """Should initialize with default config."""
        workflow = BindCraftWorkflow()
        assert workflow.config.n_trajectories == 50

    def test_init_with_custom_config(self):
        """Should accept custom config."""
        config = BindCraftConfig(n_trajectories=100)
        workflow = BindCraftWorkflow(config)
        assert workflow.config.n_trajectories == 100

    def test_resume_creates_run(self):
        """Should create a run object for tracking."""
        workflow = BindCraftWorkflow()
        run = workflow.resume("test-run-id")
        assert run.run_id == "test-run-id"
        assert run.output_path == "/output/test-run-id"
