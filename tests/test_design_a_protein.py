"""Tests for Design-A-Protein workflow adapter."""

from unittest.mock import MagicMock, patch

import pytest

from adaptyv.workflows.design_a_protein import (
    DesignAProteinConfig,
    DesignAProteinDesign,
    DesignAProteinRun,
    DesignAProteinWorkflow,
)


class TestDesignAProteinDesign:
    """Tests for DesignAProteinDesign dataclass."""

    def test_design_creation(self):
        """Should create a design with required fields."""
        design = DesignAProteinDesign(
            design_id="abc12345-001",
            sequence="MVKVGVNG",
            structure_path="/vol/test/structure.pdb",
        )
        assert design.design_id == "abc12345-001"
        assert design.sequence == "MVKVGVNG"
        assert design.structure_path == "/vol/test/structure.pdb"
        assert design.status == "pending"

    def test_design_with_metrics(self):
        """Should store metrics."""
        design = DesignAProteinDesign(
            design_id="abc12345-001",
            sequence="MVKVGVNG",
            structure_path="/vol/test/structure.pdb",
            metrics={"mpnn_score": 0.95, "shape_complementarity": 0.72},
            status="completed",
        )
        assert design.metrics["mpnn_score"] == 0.95
        assert design.metrics["shape_complementarity"] == 0.72
        assert design.status == "completed"

    def test_design_to_dict(self):
        """Should convert to dict."""
        design = DesignAProteinDesign(
            design_id="abc12345-001",
            sequence="MVKVGVNG",
            structure_path="/vol/test/structure.pdb",
            metrics={"mpnn_score": 0.95},
        )
        d = design.to_dict()
        assert d["design_id"] == "abc12345-001"
        assert d["sequence"] == "MVKVGVNG"
        assert d["structure_path"] == "/vol/test/structure.pdb"
        assert d["metrics"]["mpnn_score"] == 0.95

    def test_design_from_dict(self):
        """Should create from dict."""
        data = {
            "design_id": "test-001",
            "sequence": "MVKVGVNG",
            "structure_path": "/vol/test/s.pdb",
            "metrics": {"mpnn_score": 0.95},
            "status": "completed",
        }
        design = DesignAProteinDesign.from_dict(data)
        assert design.design_id == "test-001"
        assert design.sequence == "MVKVGVNG"
        assert design.status == "completed"

    def test_design_from_dict_defaults(self):
        """Should use defaults for missing fields."""
        data = {"design_id": "test-001"}
        design = DesignAProteinDesign.from_dict(data)
        assert design.design_id == "test-001"
        assert design.sequence == ""
        assert design.structure_path is None
        assert design.status == "pending"


class TestDesignAProteinConfig:
    """Tests for DesignAProteinConfig dataclass."""

    def test_default_config(self):
        """Should have sensible defaults."""
        config = DesignAProteinConfig()
        assert config.hotspots == []
        assert config.contig_map == ""
        assert config.chain_lengths == (50, 100)
        assert config.num_samples == 1
        assert config.temperature == 0.1
        assert config.modal_app_name == "proteindesign-demo"
        assert config.modal_function_name == "run_dap_streaming"
        assert config.output_volume == "proteindesign-demo"

    def test_custom_config(self):
        """Should accept custom values."""
        config = DesignAProteinConfig(
            hotspots=["A50", "A123", "A205"],
            contig_map="A1-413",
            chain_lengths=(80, 120),
            num_samples=10,
            temperature=0.2,
        )
        assert config.hotspots == ["A50", "A123", "A205"]
        assert config.contig_map == "A1-413"
        assert config.chain_lengths == (80, 120)
        assert config.num_samples == 10
        assert config.temperature == 0.2

    def test_validation_num_samples(self):
        """Should reject invalid num_samples."""
        with pytest.raises(ValueError, match="num_samples must be >= 1"):
            DesignAProteinConfig(num_samples=0)

    def test_validation_batch_size(self):
        """Should reject invalid batch_size."""
        with pytest.raises(ValueError, match="batch_size must be >= 1"):
            DesignAProteinConfig(batch_size=0)

    def test_validation_chain_lengths(self):
        """Should reject invalid chain_lengths."""
        with pytest.raises(ValueError, match="chain_lengths must be a tuple"):
            DesignAProteinConfig(chain_lengths=(50,))  # type: ignore

    def test_validation_chain_lengths_order(self):
        """Should reject chain_lengths where min > max."""
        with pytest.raises(
            ValueError, match="chain_lengths\\[0\\] must be <= chain_lengths\\[1\\]"
        ):
            DesignAProteinConfig(chain_lengths=(100, 50))

    def test_validation_temperature(self):
        """Should reject invalid temperature."""
        with pytest.raises(ValueError, match="temperature must be > 0"):
            DesignAProteinConfig(temperature=0)


class TestDesignAProteinRun:
    """Tests for DesignAProteinRun dataclass."""

    def test_run_creation(self):
        """Should create a run with required fields."""
        config = DesignAProteinConfig()
        run = DesignAProteinRun(
            run_id="abc123",
            output_path="/output/abc123",
            config=config,
        )
        assert run.run_id == "abc123"
        assert run.output_path == "/output/abc123"

    def test_volume_path_conversion(self):
        """Should convert container path to volume path."""
        config = DesignAProteinConfig()
        run = DesignAProteinRun(
            run_id="abc123",
            output_path="/output/abc123",
            config=config,
        )
        assert run._volume_path("/output/abc123") == "/abc123"
        assert run._volume_path("/abc123") == "/abc123"

    def test_get_status_from_volume(self):
        """Should read status from Modal volume."""
        config = DesignAProteinConfig()
        run = DesignAProteinRun(
            run_id="test123",
            output_path="/output/test123",
            config=config,
        )

        # Mock Modal volume
        mock_vol = MagicMock()
        mock_vol.read_file.return_value = iter(
            [b'{"run_id": "test123", "status": "running", "designs_completed": 2}']
        )

        with patch("modal.Volume.from_name", return_value=mock_vol):
            status = run.get_status()

        assert status["run_id"] == "test123"
        assert status["status"] == "running"
        assert status["designs_completed"] == 2

    def test_get_status_includes_error_and_resume_hint(self):
        """Should pass through error and resume_hint fields from status.json."""
        config = DesignAProteinConfig()
        run = DesignAProteinRun(
            run_id="test123",
            output_path="/output/test123",
            config=config,
        )

        mock_vol = MagicMock()
        mock_vol.read_file.return_value = iter(
            [
                b"""{
                "run_id": "test123",
                "status": "failed",
                "error": {
                    "code": "dap_failed",
                    "message": "Structure generation failed",
                    "stage": "structures",
                    "retryable": true
                },
                "resume_hint": {
                    "stage": "structures",
                    "message": "Resume from structures",
                    "retryable": true
                }
            }"""
            ]
        )

        with patch("modal.Volume.from_name", return_value=mock_vol):
            status = run.get_status()

        assert status["status"] == "failed"
        assert status["error"]["code"] == "dap_failed"
        assert status["error"]["stage"] == "structures"
        assert status["resume_hint"]["stage"] == "structures"

    def test_get_status_pending_when_not_found(self):
        """Should return pending status when file not found."""
        config = DesignAProteinConfig()
        run = DesignAProteinRun(
            run_id="test123",
            output_path="/output/test123",
            config=config,
        )

        # Mock Modal volume with file not found
        mock_vol = MagicMock()
        mock_vol.read_file.side_effect = FileNotFoundError()

        with patch("modal.Volume.from_name", return_value=mock_vol):
            status = run.get_status()

        assert status["status"] == "pending"
        assert status["run_id"] == "test123"

    def test_get_designs_from_volume(self):
        """Should read designs from Modal volume."""
        config = DesignAProteinConfig()
        run = DesignAProteinRun(
            run_id="test123",
            output_path="/output/test123",
            config=config,
        )

        # Mock design entry
        mock_entry = MagicMock()
        mock_entry.path = "test123/designs/design-001"

        # Mock Modal volume
        mock_vol = MagicMock()
        mock_vol.listdir.return_value = [mock_entry]
        mock_vol.read_file.return_value = iter(
            [
                b'{"design_id": "design-001", "sequence": "MVKVG", "structure_path": "/vol/test/structure.pdb", "status": "completed"}'
            ]
        )

        with patch("modal.Volume.from_name", return_value=mock_vol):
            designs = run.get_designs()

        assert len(designs) == 1
        assert designs[0].design_id == "design-001"
        assert designs[0].sequence == "MVKVG"

    def test_get_designs_empty_when_not_found(self):
        """Should return empty list when designs directory not found."""
        config = DesignAProteinConfig()
        run = DesignAProteinRun(
            run_id="test123",
            output_path="/output/test123",
            config=config,
        )

        # Mock Modal volume with directory not found
        mock_vol = MagicMock()
        mock_vol.listdir.side_effect = FileNotFoundError()

        with patch("modal.Volume.from_name", return_value=mock_vol):
            designs = run.get_designs()

        assert designs == []


class TestDesignAProteinWorkflow:
    """Tests for DesignAProteinWorkflow class."""

    def test_init_with_default_config(self):
        """Should initialize with default config."""
        workflow = DesignAProteinWorkflow()
        assert workflow.config.num_samples == 1
        assert workflow.config.modal_app_name == "proteindesign-demo"

    def test_init_with_custom_config(self):
        """Should accept custom config."""
        config = DesignAProteinConfig(
            num_samples=5,
            modal_app_name="custom-app",
        )
        workflow = DesignAProteinWorkflow(config)
        assert workflow.config.num_samples == 5
        assert workflow.config.modal_app_name == "custom-app"

    def test_start_spawns_modal_function(self):
        """Should spawn Modal function with config params."""
        # Mock Modal function lookup and spawn
        mock_fn = MagicMock()

        with patch("modal.Function.from_name", return_value=mock_fn):
            config = DesignAProteinConfig(
                hotspots=["A50", "A123"],
                contig_map="A1-413",
                num_samples=4,
                temperature=0.2,
            )
            workflow = DesignAProteinWorkflow(config)
            run = workflow.start(target_pdb="https://files.rcsb.org/view/2VSM.pdb")

        # Should spawn the streaming function
        assert mock_fn.spawn.call_count == 1

        # Check spawn was called with correct params
        call_kwargs = mock_fn.spawn.call_args.kwargs
        assert call_kwargs["target_pdb_url"] == "https://files.rcsb.org/view/2VSM.pdb"
        assert call_kwargs["hotspots"] == ["A50", "A123"]
        assert call_kwargs["contig_map"] == "A1-413"
        assert call_kwargs["num_samples"] == 4
        assert call_kwargs["temperature"] == 0.2

        # Run should be created
        assert run.run_id
        assert run.output_path.startswith("/output/")

    def test_resume_creates_run(self):
        """Should create run object for existing run."""
        workflow = DesignAProteinWorkflow()
        run = workflow.resume("existing-run-id")

        assert run.run_id == "existing-run-id"
        assert run.output_path == "/output/existing-run-id"


@pytest.mark.slow
class TestDesignAProteinWorkflowIntegration:
    """Integration tests that require real Modal connection.

    These tests are marked slow and require:
    - MODAL_TOKEN_ID and MODAL_TOKEN_SECRET environment variables
    - Access to the proteindesign-demo Modal app

    Run with: pytest -m slow
    """

    def test_start_real_modal(self):
        """Should spawn real Modal jobs (requires Modal auth)."""
        pytest.skip("Requires Modal auth - run manually with proper credentials")

        config = DesignAProteinConfig(
            hotspots=["A50"],
            contig_map="A1-413",
            num_samples=1,
        )
        workflow = DesignAProteinWorkflow(config)
        run = workflow.start(target_pdb="https://files.rcsb.org/view/2VSM.pdb")

        assert run.run_id
        assert run.output_path
