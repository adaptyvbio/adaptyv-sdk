"""Results types for BO/AL consumption.

Types for feeding experiment results into Bayesian optimization and active learning loops.
Results must be fetched manually via the Foundry Portal and parsed using `parse_data_package()`.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, computed_field


class FailurePoint(str, Enum):
    """Where in the pipeline the sequence failed - for BO/AL feedback.

    This is the PRIMARY enum for Bayesian optimization and active learning.
    Use this when feeding results back into the design loop.

    Pipeline stages:
        Stage 1: Generation -> GENERATION_FAILED
        Stage 2: Auto-filter -> FILTERED_AUTO
        Stage 3: Human review -> REVIEWER_DENIED
        Stage 5: Experiment -> NO_EXPRESSION | NO_BINDING | UNKNOWN_BAD | SUCCESS

    For internal status tracking during workflow, use ResultStatus from
    types.internal instead.
    """

    GENERATION_FAILED = "generation_failed"  # Design pipeline failed
    FILTERED_AUTO = "filtered_auto"  # Stage 2: auto-filter removed
    REVIEWER_DENIED = "reviewer_denied"  # Stage 3: human review rejected
    NO_EXPRESSION = "no_expression"  # Stage 5: didn't express
    NO_BINDING = "no_binding"  # Stage 5: expressed but didn't bind
    UNKNOWN_BAD = "unknown_bad"  # Failed for unknown reason
    SUCCESS = "success"  # Binding confirmed


class SequenceOutcome(BaseModel):
    """Single sequence result for BO/AL consumption.

    This is the primary type for feeding results into Bayesian optimization
    or active learning loops.
    """

    sequence_name: str
    sequence: str
    status: FailurePoint

    # Binding data (if measured)
    kd_value: float | None = None  # Dissociation constant (M)
    kon: float | None = None  # Association rate (1/Ms)
    koff: float | None = None  # Dissociation rate (1/s)

    # Expression data
    expression_level: float | None = None  # Relative expression level

    # Design metrics (from generation stage)
    plddt: float | None = None
    iptm: float | None = None
    ipsae: float | None = None
    shape_complementarity: float | None = None

    # AL configuration
    use_for_active_learning: bool = True  # Include in AL training?
    al_label: float | None = None  # Numeric label for AL (-1 for negative, KD for positive)

    @computed_field
    @property
    def is_positive(self) -> bool:
        """Whether this is a positive example for AL."""
        return self.status == FailurePoint.SUCCESS

    @computed_field
    @property
    def is_hard_negative(self) -> bool:
        """Whether this is a hard negative (expression failed)."""
        return self.status == FailurePoint.NO_EXPRESSION


class ExperimentOutcomes(BaseModel):
    """Full results for BO loop consumption.

    Aggregates all sequence outcomes from an experiment with summary statistics.
    """

    experiment_id: str
    predecessor_id: str | None = None  # For tracking experiment lineage
    round_number: int = 1

    # All sequences with outcomes
    sequences: list[SequenceOutcome]

    # Aggregated stats
    total_submitted: int
    total_measured: int
    total_success: int

    @computed_field
    @property
    def success_rate(self) -> float:
        """Fraction of measured sequences that bound."""
        if self.total_measured == 0:
            return 0.0
        return self.total_success / self.total_measured

    @computed_field
    @property
    def expression_rate(self) -> float:
        """Fraction of submitted sequences that expressed."""
        if self.total_submitted == 0:
            return 0.0
        no_expression = sum(1 for s in self.sequences if s.status == FailurePoint.NO_EXPRESSION)
        return 1.0 - (no_expression / self.total_submitted)

    # For next round planning
    recommended_upsize_factor: float = 1.0

    @property
    def positives(self) -> list[SequenceOutcome]:
        """All sequences with confirmed binding."""
        return [s for s in self.sequences if s.status == FailurePoint.SUCCESS]

    @property
    def negatives_for_al(self) -> list[SequenceOutcome]:
        """All failures usable for active learning training."""
        usable_statuses = {FailurePoint.NO_BINDING, FailurePoint.NO_EXPRESSION}
        return [
            s for s in self.sequences if s.status in usable_statuses and s.use_for_active_learning
        ]

    @property
    def excluded(self) -> list[SequenceOutcome]:
        """Sequences excluded from AL (reviewer denied, unknown)."""
        excluded_statuses = {FailurePoint.REVIEWER_DENIED, FailurePoint.UNKNOWN_BAD}
        return [s for s in self.sequences if s.status in excluded_statuses]
