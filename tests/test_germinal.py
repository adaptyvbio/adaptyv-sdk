"""Tests for Germinal workflow adapter."""

from unittest.mock import MagicMock, patch

import pytest

from adaptyv.workflows.germinal import (
    GerminalAdvancedConfig,
    GerminalConfig,
    GerminalDesign,
    GerminalRun,
    GerminalWorkflow,
)


class TestGerminalDesign:
    """Tests for GerminalDesign dataclass."""

    def test_design_creation(self):
        """Should create a design with required fields."""
        design = GerminalDesign(
            design_id="0001",
            sequence="MVKVGVNG",
        )
        assert design.design_id == "0001"
        assert design.sequence == "MVKVGVNG"
        assert design.status == "pending"
        assert design.structure_path is None
        assert design.metrics == {}
        assert design.kind == "parent"
        assert design.spec == {}
        assert design.created_at is None

    def test_design_with_metrics(self):
        """Should store metrics."""
        design = GerminalDesign(
            design_id="0001",
            sequence="MVKVGVNG",
            metrics={"plddt": 85.2, "iptm": 0.78, "ipsae_d0chn_min": 0.65},
            status="completed",
        )
        assert design.metrics["plddt"] == 85.2
        assert design.metrics["iptm"] == 0.78
        assert design.metrics["ipsae_d0chn_min"] == 0.65
        assert design.status == "completed"

    def test_design_with_structure_path(self):
        """Should store structure path."""
        design = GerminalDesign(
            design_id="0001",
            sequence="MVKVGVNG",
            structure_path="/output/run123/designs/0001/structure.pdb",
        )
        assert design.structure_path == "/output/run123/designs/0001/structure.pdb"

    def test_design_kinds(self):
        """Should support parent and child kinds."""
        parent = GerminalDesign(design_id="001", sequence="ABC", kind="parent")
        child = GerminalDesign(design_id="002", sequence="DEF", kind="child")
        assert parent.kind == "parent"
        assert child.kind == "child"

    def test_design_to_dict(self):
        """Should convert to dict."""
        design = GerminalDesign(
            design_id="0001",
            sequence="MVKVGVNG",
            structure_path="/path/to/structure.pdb",
            metrics={"plddt": 85.0},
            status="completed",
            kind="child",
            spec={"cdr3": "CARWGM"},
            created_at="2024-01-01T00:00:00",
        )
        d = design.to_dict()
        assert d["design_id"] == "0001"
        assert d["sequence"] == "MVKVGVNG"
        assert d["structure_path"] == "/path/to/structure.pdb"
        assert d["metrics"]["plddt"] == 85.0
        assert d["status"] == "completed"
        assert d["kind"] == "child"
        assert d["spec"]["cdr3"] == "CARWGM"
        assert d["created_at"] == "2024-01-01T00:00:00"

    def test_design_from_dict(self):
        """Should create from dict."""
        data = {
            "design_id": "0001",
            "sequence": "MVKVGVNG",
            "structure_path": "/path/to/structure.pdb",
            "metrics": {"plddt": 85.0},
            "status": "completed",
            "kind": "child",
            "spec": {"cdr3": "CARWGM"},
            "created_at": "2024-01-01T00:00:00",
        }
        design = GerminalDesign.from_dict(data)
        assert design.design_id == "0001"
        assert design.sequence == "MVKVGVNG"
        assert design.kind == "child"

    def test_design_from_dict_defaults(self):
        """Should use defaults for missing fields."""
        data = {"design_id": "0001", "sequence": "MVKVGVNG"}
        design = GerminalDesign.from_dict(data)
        assert design.status == "pending"
        assert design.kind == "parent"
        assert design.metrics == {}


class TestGerminalAdvancedConfig:
    """Tests for GerminalAdvancedConfig dataclass."""

    def test_default_config(self):
        """Should have sensible defaults."""
        config = GerminalAdvancedConfig()
        assert config.logits_steps == 65
        assert config.softmax_steps == 35
        assert config.search_steps == 10
        assert config.weights_plddt == 1.0
        assert config.weights_iptm == 0.75
        assert config.backend == "freebindcraft"
        assert config.no_initial_filters is False
        assert config.no_final_filters is False

    def test_custom_config(self):
        """Should accept custom values."""
        config = GerminalAdvancedConfig(
            logits_steps=30,
            softmax_steps=20,
            search_steps=5,
            backend="pyrosetta",
            no_initial_filters=True,
        )
        assert config.logits_steps == 30
        assert config.softmax_steps == 20
        assert config.search_steps == 5
        assert config.backend == "pyrosetta"
        assert config.no_initial_filters is True


class TestGerminalConfig:
    """Tests for GerminalConfig dataclass."""

    def test_default_config(self):
        """Should have sensible defaults."""
        config = GerminalConfig()
        assert config.target_name == "pdl1"
        assert config.binder_format == "vhh"
        assert config.design_mode == "both"
        assert config.max_trajectories == 10
        assert config.num_seqs == 40
        assert config.advanced is None
        assert config.output_volume == "mosaic-outputs"

    def test_custom_config(self):
        """Should accept custom values."""
        config = GerminalConfig(
            binder_format="scfv",
            design_mode="template",
            max_trajectories=20,
        )
        assert config.binder_format == "scfv"
        assert config.design_mode == "template"
        assert config.max_trajectories == 20

    def test_with_advanced_config(self):
        """Should accept advanced config."""
        advanced = GerminalAdvancedConfig(logits_steps=30)
        config = GerminalConfig(advanced=advanced)
        assert config.advanced is not None
        assert config.advanced.logits_steps == 30

    def test_invalid_target_name(self):
        """Should reject non-pdl1 targets in MVP."""
        with pytest.raises(ValueError, match="target_name must be 'pdl1'"):
            GerminalConfig(target_name="bbf14")

    def test_invalid_binder_format(self):
        """Should reject invalid binder format."""
        with pytest.raises(ValueError, match="binder_format must be 'vhh' or 'scfv'"):
            GerminalConfig(binder_format="fab")

    def test_invalid_design_mode(self):
        """Should reject invalid design mode."""
        with pytest.raises(ValueError, match="design_mode must be"):
            GerminalConfig(design_mode="random")

    def test_invalid_max_trajectories(self):
        """Should reject max_trajectories < 1."""
        with pytest.raises(ValueError, match="max_trajectories must be >= 1"):
            GerminalConfig(max_trajectories=0)


class TestGerminalRun:
    """Tests for GerminalRun dataclass."""

    def test_run_creation(self):
        """Should create a run with required fields."""
        run = GerminalRun(
            run_id="abc123",
            output_path="/output/abc123",
        )
        assert run.run_id == "abc123"
        assert run.output_path == "/output/abc123"
        assert run.output_volume == "mosaic-outputs"

    def test_run_with_custom_volume(self):
        """Should accept custom output volume."""
        run = GerminalRun(
            run_id="abc123",
            output_volume="custom-volume",
            output_path="/output/abc123",
        )
        assert run.output_volume == "custom-volume"

    def test_get_status_includes_error_and_resume_hint(self):
        """Should pass through error and resume_hint fields from status.json."""
        run = GerminalRun(
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
                    "code": "germinal_failed",
                    "message": "Filtering failed",
                    "stage": "filters",
                    "retryable": true
                },
                "resume_hint": {
                    "stage": "filters",
                    "message": "Resume at filters",
                    "retryable": true
                }
            }"""
            ]
        )

        with patch("modal.Volume.from_name", return_value=mock_vol):
            status = run.get_status()

        assert status["status"] == "failed"
        assert status["error"]["code"] == "germinal_failed"
        assert status["error"]["stage"] == "filters"
        assert status["resume_hint"]["stage"] == "filters"


class TestGerminalWorkflow:
    """Tests for GerminalWorkflow class."""

    def test_init_with_default_config(self):
        """Should initialize with default config."""
        workflow = GerminalWorkflow()
        assert workflow.config.target_name == "pdl1"
        assert workflow.config.binder_format == "vhh"
        assert workflow.config.max_trajectories == 10

    def test_init_with_custom_config(self):
        """Should accept custom config."""
        config = GerminalConfig(max_trajectories=20, binder_format="scfv")
        workflow = GerminalWorkflow(config)
        assert workflow.config.max_trajectories == 20
        assert workflow.config.binder_format == "scfv"

    def test_resume_creates_run(self):
        """Should create a run object for tracking."""
        workflow = GerminalWorkflow()
        run = workflow.resume("test-run-id")
        assert run.run_id == "test-run-id"
        assert run.output_path == "/output/test-run-id"
        # Uses config's output_volume which is mosaic-outputs
        assert run.output_volume == "mosaic-outputs"

    def test_resume_with_custom_volume(self):
        """Should use config's output volume."""
        config = GerminalConfig()
        config.output_volume = "custom-volume"
        workflow = GerminalWorkflow(config)
        run = workflow.resume("test-run-id")
        assert run.output_volume == "custom-volume"
