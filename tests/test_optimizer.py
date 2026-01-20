"""Tests for parameter optimization hints."""

import pytest

from adaptyv.workflows.optimizer import (
    OptimizationHints,
    TargetAnalysis,
    analyze_target,
    get_optimization_hints,
)

# Sample PDB content for testing
SMALL_PDB = """ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N
ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00 20.00           C
ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00 20.00           C
ATOM      4  O   ALA A   1       1.245   2.390   0.000  1.00 20.00           O
ATOM      5  N   LEU A   2       3.300   1.550   0.000  1.00 20.00           N
ATOM      6  CA  LEU A   2       3.950   2.850   0.000  1.00 20.00           C
ATOM      7  N   ILE A   3       5.000   3.000   0.000  1.00 20.00           N
ATOM      8  CA  ILE A   3       6.000   4.000   0.000  1.00 20.00           C
END
"""

MEDIUM_PDB_HYDROPHOBIC = """ATOM      1  N   ALA A   1       0.0   0.0   0.0  1.00  0.00           N
ATOM      2  N   LEU A   2       1.0   0.0   0.0  1.00  0.00           N
ATOM      3  N   ILE A   3       2.0   0.0   0.0  1.00  0.00           N
ATOM      4  N   VAL A   4       3.0   0.0   0.0  1.00  0.00           N
ATOM      5  N   PHE A   5       4.0   0.0   0.0  1.00  0.00           N
ATOM      6  N   TRP A   6       5.0   0.0   0.0  1.00  0.00           N
ATOM      7  N   MET A   7       6.0   0.0   0.0  1.00  0.00           N
ATOM      8  N   PRO A   8       7.0   0.0   0.0  1.00  0.00           N
ATOM      9  N   SER A   9       8.0   0.0   0.0  1.00  0.00           N
ATOM     10  N   THR A  10       9.0   0.0   0.0  1.00  0.00           N
END
"""


def _generate_large_pdb(residue_count: int) -> str:
    """Generate a PDB with specified number of residues."""
    lines = []
    for i in range(1, residue_count + 1):
        line = f"ATOM  {i:5d}  N   ALA A{i:4d}       0.0   0.0   0.0  1.00  0.00           N"
        lines.append(line)
    lines.append("END")
    return "\n".join(lines)


class TestTargetAnalysis:
    """Tests for TargetAnalysis dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        analysis = TargetAnalysis()
        assert analysis.residue_count == 0
        assert analysis.chain_count == 0
        assert analysis.hydrophobicity_ratio == 0.0
        assert analysis.sequence == ""


class TestAnalyzeTarget:
    """Tests for analyze_target function."""

    def test_small_pdb(self):
        """Should parse small PDB correctly."""
        analysis = analyze_target(SMALL_PDB)
        assert analysis.residue_count == 3  # ALA, LEU, ILE
        assert analysis.chain_count == 1
        assert analysis.sequence == "ALI"

    def test_hydrophobic_pdb(self):
        """Should calculate hydrophobicity ratio."""
        analysis = analyze_target(MEDIUM_PDB_HYDROPHOBIC)
        assert analysis.residue_count == 10
        # 8 hydrophobic (ALIVFWMP) + 2 polar (ST)
        assert analysis.hydrophobicity_ratio == 0.8

    def test_empty_pdb(self):
        """Should handle empty PDB."""
        analysis = analyze_target("")
        assert analysis.residue_count == 0
        assert analysis.hydrophobicity_ratio == 0.0

    def test_invalid_pdb(self):
        """Should handle invalid PDB content."""
        analysis = analyze_target("not a pdb file\nsome random text")
        assert analysis.residue_count == 0

    def test_large_pdb(self):
        """Should handle large PDB files."""
        pdb = _generate_large_pdb(500)
        analysis = analyze_target(pdb)
        assert analysis.residue_count == 500
        assert len(analysis.sequence) == 500


class TestOptimizationHints:
    """Tests for OptimizationHints dataclass."""

    def test_to_dict(self):
        """Should convert to dict correctly."""
        hints = OptimizationHints(
            chain_lengths=(60, 120),
            temperature=0.15,
            num_samples=10,
            batch_size=2,
            n_trajectories=2,
            confidence=0.8,
        )
        hints.explanations["chain_lengths"] = "Based on target size"
        hints.warnings.append("Test warning")

        d = hints.to_dict()
        assert d["chain_lengths"] == [60, 120]
        assert d["temperature"] == 0.15
        assert d["num_samples"] == 10
        assert d["batch_size"] == 2
        assert d["n_trajectories"] == 2
        assert d["confidence"] == 0.8
        assert "chain_lengths" in d["explanations"]
        assert "Test warning" in d["warnings"]

    def test_to_dict_omits_none(self):
        """Should omit None values from dict."""
        hints = OptimizationHints(temperature=0.1)
        d = hints.to_dict()
        assert "chain_lengths" not in d
        assert "num_samples" not in d
        assert "temperature" in d


class TestGetOptimizationHints:
    """Tests for get_optimization_hints function."""

    def test_invalid_workflow_type(self):
        """Should reject invalid workflow type."""
        with pytest.raises(ValueError, match="Unknown workflow_type"):
            get_optimization_hints(
                target_pdb="https://example.com/test.pdb",
                workflow_type="invalid",
            )

    def test_invalid_compute_budget(self):
        """Should reject invalid compute budget."""
        with pytest.raises(ValueError, match="Unknown compute_budget"):
            get_optimization_hints(
                target_pdb="https://example.com/test.pdb",
                workflow_type="design_a_protein",
                compute_budget="invalid",
            )

    def test_dap_without_pdb_content(self):
        """Should return budget-based hints without PDB content."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            compute_budget="balanced",
        )

        assert hints.chain_lengths == (50, 120)  # Default
        assert hints.temperature == 0.1
        assert hints.num_samples == 8  # Balanced budget
        assert hints.batch_size == 2
        assert hints.confidence == 0.5  # Lower confidence without target

    def test_dap_with_small_target(self):
        """Should recommend smaller binders for small targets."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            pdb_content=SMALL_PDB,
        )

        # Small target (3 residues) should get small binder recommendation
        assert hints.chain_lengths == (40, 80)
        assert hints.confidence == 0.7

    def test_dap_with_large_target(self):
        """Should recommend larger binders for large targets."""
        large_pdb = _generate_large_pdb(400)
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            pdb_content=large_pdb,
        )

        # Large target should get larger binder recommendation
        assert hints.chain_lengths[0] >= 70
        assert hints.chain_lengths[1] >= 150

    def test_dap_with_hydrophobic_target(self):
        """Should increase temperature for hydrophobic targets."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            pdb_content=MEDIUM_PDB_HYDROPHOBIC,
        )

        # Hydrophobic target (80%) should have higher temperature
        assert hints.temperature > 0.1

    def test_dap_fast_budget(self):
        """Should recommend fewer samples for fast budget."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            compute_budget="fast",
        )

        assert hints.num_samples == 3
        assert hints.batch_size == 4
        assert hints.n_trajectories == 1

    def test_dap_thorough_budget(self):
        """Should recommend more samples for thorough budget."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            compute_budget="thorough",
        )

        assert hints.num_samples == 20
        assert hints.batch_size == 1
        assert hints.n_trajectories == 4

    def test_dap_low_success_rate(self):
        """Should adjust parameters for low success rate."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            compute_budget="balanced",
            previous_success_rate=0.1,
        )

        # Low success rate should increase diversity
        assert hints.temperature >= 0.15  # Higher temp for diversity
        assert hints.num_samples >= 8  # More samples

    def test_bindcraft_hints(self):
        """Should return BindCraft-specific hints."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="bindcraft",
            compute_budget="balanced",
        )

        assert hints.num_samples == 8
        assert "num_samples" in hints.explanations

    def test_bindcraft_with_target(self):
        """Should analyze target for BindCraft."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="bindcraft",
            pdb_content=SMALL_PDB,
        )

        assert hints.chain_lengths is not None
        assert hints.confidence == 0.6

    def test_germinal_hints(self):
        """Should return Germinal-specific hints."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="germinal",
            compute_budget="balanced",
        )

        assert hints.num_samples == 8
        assert hints.temperature is not None
        assert "nanobody" in hints.explanations.get("num_samples", "").lower()

    def test_germinal_small_target_warning(self):
        """Should warn about small targets for Germinal."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="germinal",
            pdb_content=SMALL_PDB,
        )

        # Small target should trigger warning about nanobody size
        assert any("small" in w.lower() or "nanobod" in w.lower() for w in hints.warnings)

    def test_explanations_provided(self):
        """Should provide explanations for all hints."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            compute_budget="balanced",
        )

        assert "chain_lengths" in hints.explanations
        assert "temperature" in hints.explanations
        assert "num_samples" in hints.explanations
        assert "batch_size" in hints.explanations

    def test_invalid_pdb_content_warning(self):
        """Should warn when PDB content cannot be parsed."""
        hints = get_optimization_hints(
            target_pdb="https://example.com/test.pdb",
            workflow_type="design_a_protein",
            pdb_content="invalid pdb content",
        )

        assert any("parse" in w.lower() or "residue" in w.lower() for w in hints.warnings)
