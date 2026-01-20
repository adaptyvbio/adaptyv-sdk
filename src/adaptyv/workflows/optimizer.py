"""Parameter optimization hints for protein design workflows.

Provides recommendations for workflow parameters based on:
- Target characteristics (size, hydrophobicity)
- Previous results (success rates)
- Compute budget constraints (time, GPU availability)

Usage:
    from adaptyv.workflows.optimizer import get_optimization_hints

    hints = get_optimization_hints(
        target_pdb="https://files.rcsb.org/view/2VSM.pdb",
        workflow_type="design_a_protein",
        compute_budget="balanced",
    )

    # Apply hints to config
    config = DesignAProteinConfig(
        chain_lengths=hints.chain_lengths,
        temperature=hints.temperature,
        num_samples=hints.num_samples,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ComputeBudget = Literal["fast", "balanced", "thorough"]
WorkflowType = Literal["design_a_protein", "bindcraft", "germinal"]

# Hydrophobic amino acids for calculating hydrophobicity ratio
HYDROPHOBIC_RESIDUES = frozenset("AILMFWVP")


@dataclass
class TargetAnalysis:
    """Analysis of target PDB characteristics."""

    residue_count: int = 0
    chain_count: int = 0
    hydrophobicity_ratio: float = 0.0
    sequence: str = ""


@dataclass
class OptimizationHints:
    """Parameter optimization hints for a workflow.

    All fields are optional - only populated when a recommendation is relevant.
    """

    # Structure generation hints
    chain_lengths: tuple[int, int] | None = None
    n_trajectories: int | None = None
    num_samples: int | None = None
    batch_size: int | None = None

    # Sequence design hints
    temperature: float | None = None

    # Explanations for each hint
    explanations: dict[str, str] = field(default_factory=dict)

    # Confidence in hints (0.0-1.0)
    confidence: float = 0.5

    # Warnings or notes
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {}
        if self.chain_lengths is not None:
            result["chain_lengths"] = list(self.chain_lengths)
        if self.n_trajectories is not None:
            result["n_trajectories"] = self.n_trajectories
        if self.num_samples is not None:
            result["num_samples"] = self.num_samples
        if self.batch_size is not None:
            result["batch_size"] = self.batch_size
        if self.temperature is not None:
            result["temperature"] = self.temperature
        result["explanations"] = self.explanations
        result["confidence"] = self.confidence
        if self.warnings:
            result["warnings"] = self.warnings
        return result


def analyze_target(pdb_content: str) -> TargetAnalysis:
    """Analyze target PDB content to extract characteristics.

    Args:
        pdb_content: Raw PDB file content as string.

    Returns:
        TargetAnalysis with extracted characteristics.
    """
    residue_count = 0
    chains: set[str] = set()
    sequence_residues: list[str] = []
    seen_residues: set[tuple[str, int]] = set()

    for line in pdb_content.split("\n"):
        if line.startswith("ATOM"):
            try:
                chain = line[21]
                res_seq = int(line[22:26].strip())
                res_name = line[17:20].strip()

                key = (chain, res_seq)
                if key not in seen_residues:
                    seen_residues.add(key)
                    residue_count += 1
                    chains.add(chain)
                    one_letter = _three_to_one(res_name)
                    if one_letter:
                        sequence_residues.append(one_letter)
            except (ValueError, IndexError):
                continue

    sequence = "".join(sequence_residues)
    hydrophobic_count = sum(1 for r in sequence if r in HYDROPHOBIC_RESIDUES)
    hydrophobicity_ratio = hydrophobic_count / len(sequence) if sequence else 0.0

    return TargetAnalysis(
        residue_count=residue_count,
        chain_count=len(chains),
        hydrophobicity_ratio=hydrophobicity_ratio,
        sequence=sequence,
    )


def _three_to_one(three_letter: str) -> str:
    """Convert three-letter amino acid code to one-letter."""
    mapping = {
        "ALA": "A",
        "CYS": "C",
        "ASP": "D",
        "GLU": "E",
        "PHE": "F",
        "GLY": "G",
        "HIS": "H",
        "ILE": "I",
        "LYS": "K",
        "LEU": "L",
        "MET": "M",
        "ASN": "N",
        "PRO": "P",
        "GLN": "Q",
        "ARG": "R",
        "SER": "S",
        "THR": "T",
        "VAL": "V",
        "TRP": "W",
        "TYR": "Y",
    }
    return mapping.get(three_letter.upper(), "")


def _recommend_chain_lengths(target: TargetAnalysis) -> tuple[int, int]:
    """Recommend binder chain lengths based on target size.

    Heuristic: Binders should be roughly 15-40% of target size,
    with minimum of 50 and maximum of 200 residues.
    """
    target_size = target.residue_count

    if target_size < 100:
        # Small target: use small binders
        return (40, 80)
    elif target_size < 300:
        # Medium target: standard binder size
        return (50, 120)
    elif target_size < 600:
        # Large target: larger binders may be needed
        return (70, 150)
    else:
        # Very large target
        return (80, 180)


def _recommend_temperature(
    target: TargetAnalysis,
    previous_success_rate: float | None = None,
) -> float:
    """Recommend LigandMPNN temperature based on target and history.

    Lower temperature (0.05-0.1) = more confident, less diverse sequences.
    Higher temperature (0.2-0.5) = more diverse but potentially lower quality.

    Adjustments:
    - High hydrophobicity targets may need higher temp for diversity
    - Low previous success rate suggests trying higher temperature
    """
    base_temp = 0.1

    # Adjust for hydrophobicity: hydrophobic interfaces are harder
    if target.hydrophobicity_ratio > 0.4:
        base_temp += 0.05
    elif target.hydrophobicity_ratio > 0.5:
        base_temp += 0.1

    # Adjust for previous success rate
    if previous_success_rate is not None:
        if previous_success_rate < 0.1:
            # Very low success: increase diversity
            base_temp += 0.1
        elif previous_success_rate < 0.3:
            # Low success: slight increase
            base_temp += 0.05

    # Clamp to valid range
    return min(max(base_temp, 0.05), 0.5)


def _recommend_num_samples(
    compute_budget: ComputeBudget,
    previous_success_rate: float | None = None,
) -> int:
    """Recommend number of structure samples based on budget and history."""
    base_samples = {
        "fast": 3,
        "balanced": 8,
        "thorough": 20,
    }[compute_budget]

    # If previous success rate is low, generate more samples
    if previous_success_rate is not None and previous_success_rate < 0.2:
        base_samples = int(base_samples * 1.5)

    return min(base_samples, 50)  # Cap at 50


def _recommend_batch_size(compute_budget: ComputeBudget) -> int:
    """Recommend batch size based on GPU memory constraints."""
    return {
        "fast": 4,  # Larger batches for speed
        "balanced": 2,  # Standard batch size
        "thorough": 1,  # Smaller batches for stability
    }[compute_budget]


def _recommend_n_trajectories(compute_budget: ComputeBudget) -> int:
    """Recommend number of trajectories for Protpardelle."""
    return {
        "fast": 1,
        "balanced": 2,
        "thorough": 4,
    }[compute_budget]


def get_optimization_hints(
    target_pdb: str,
    workflow_type: str,
    compute_budget: str = "balanced",
    previous_success_rate: float | None = None,
    pdb_content: str | None = None,
) -> OptimizationHints:
    """Get parameter optimization hints based on target and budget.

    Args:
        target_pdb: URL to target PDB file (used for identification).
        workflow_type: Workflow type ("design_a_protein", "bindcraft", "germinal").
        compute_budget: Budget level ("fast", "balanced", "thorough").
        previous_success_rate: Optional success rate from previous runs (0.0-1.0).
        pdb_content: Optional PDB file content. If not provided, returns
            budget-based recommendations without target analysis.

    Returns:
        OptimizationHints with parameter recommendations and explanations.
    """
    # Validate inputs
    if workflow_type not in ("design_a_protein", "bindcraft", "germinal"):
        raise ValueError(
            f"Unknown workflow_type: {workflow_type}. "
            f"Expected: design_a_protein, bindcraft, germinal"
        )

    if compute_budget not in ("fast", "balanced", "thorough"):
        raise ValueError(
            f"Unknown compute_budget: {compute_budget}. Expected: fast, balanced, thorough"
        )

    budget: ComputeBudget = compute_budget  # type: ignore[assignment]
    extra_warnings: list[str] = []

    # Analyze target if content provided
    target: TargetAnalysis | None = None
    if pdb_content:
        target = analyze_target(pdb_content)
        if target.residue_count == 0:
            extra_warnings.append("Could not parse residues from PDB content")
            target = None

    # Generate recommendations based on workflow type
    if workflow_type == "design_a_protein":
        hints = _get_dap_hints(target, budget, previous_success_rate)
    elif workflow_type == "bindcraft":
        hints = _get_bindcraft_hints(target, budget, previous_success_rate)
    else:
        hints = _get_germinal_hints(target, budget, previous_success_rate)

    hints.warnings.extend(extra_warnings)
    return hints


def _get_dap_hints(
    target: TargetAnalysis | None,
    budget: ComputeBudget,
    previous_success_rate: float | None,
) -> OptimizationHints:
    """Get hints specific to Design-A-Protein workflow."""
    hints = OptimizationHints()

    # Chain lengths (target-dependent)
    if target:
        hints.chain_lengths = _recommend_chain_lengths(target)
        hints.explanations["chain_lengths"] = (
            f"Based on target size ({target.residue_count} residues). "
            f"Binders at 15-40% of target size work well."
        )
    else:
        hints.chain_lengths = (50, 120)
        hints.explanations["chain_lengths"] = (
            "Default range. Provide PDB content for target-specific recommendation."
        )

    # Temperature (target + history dependent)
    hints.temperature = _recommend_temperature(target or TargetAnalysis(), previous_success_rate)
    temp_reason = "Default temperature for balanced diversity/quality."
    if target and target.hydrophobicity_ratio > 0.4:
        temp_reason = (
            f"Slightly higher due to hydrophobic target "
            f"({target.hydrophobicity_ratio:.0%} hydrophobic residues)."
        )
    if previous_success_rate is not None and previous_success_rate < 0.3:
        temp_reason += f" Increased for diversity (previous success: {previous_success_rate:.0%})."
    hints.explanations["temperature"] = temp_reason

    # Num samples (budget + history dependent)
    hints.num_samples = _recommend_num_samples(budget, previous_success_rate)
    hints.explanations["num_samples"] = (
        f"Based on '{budget}' compute budget. "
        f"More samples increase chance of finding good structures."
    )

    # Batch size (budget dependent)
    hints.batch_size = _recommend_batch_size(budget)
    hints.explanations["batch_size"] = (
        f"Optimized for '{budget}' budget. Smaller batches are more stable but slower."
    )

    # N trajectories (budget dependent)
    hints.n_trajectories = _recommend_n_trajectories(budget)
    hints.explanations["n_trajectories"] = (
        f"Based on '{budget}' compute budget. More trajectories explore more conformational space."
    )

    hints.confidence = 0.7 if target else 0.5
    return hints


def _get_bindcraft_hints(
    target: TargetAnalysis | None,
    budget: ComputeBudget,
    previous_success_rate: float | None,
) -> OptimizationHints:
    """Get hints specific to BindCraft workflow."""
    hints = OptimizationHints()

    # BindCraft uses similar parameters to DAP
    if target:
        hints.chain_lengths = _recommend_chain_lengths(target)
        hints.explanations["chain_lengths"] = (
            f"Target size: {target.residue_count} residues. "
            f"BindCraft binders typically 50-150 residues."
        )

    hints.num_samples = _recommend_num_samples(budget, previous_success_rate)
    hints.explanations["num_samples"] = f"BindCraft sample count for '{budget}' budget."

    hints.confidence = 0.6 if target else 0.4
    return hints


def _get_germinal_hints(
    target: TargetAnalysis | None,
    budget: ComputeBudget,
    previous_success_rate: float | None,
) -> OptimizationHints:
    """Get hints specific to Germinal (VHH/nanobody) workflow."""
    hints = OptimizationHints()

    # Germinal produces fixed-size nanobodies (~120 residues)
    # Main tunable is num_samples
    hints.num_samples = _recommend_num_samples(budget, previous_success_rate)
    hints.explanations["num_samples"] = (
        f"Germinal sample count for '{budget}' budget. Nanobody size is fixed (~120 residues)."
    )

    # Temperature for sequence optimization
    hints.temperature = _recommend_temperature(target or TargetAnalysis(), previous_success_rate)
    hints.explanations["temperature"] = (
        "Controls CDR sequence diversity. Lower = more conservative mutations."
    )

    hints.confidence = 0.6
    if target and target.residue_count < 100:
        hints.warnings.append(
            "Small target detected. Germinal nanobodies may be too large for optimal binding."
        )

    return hints
