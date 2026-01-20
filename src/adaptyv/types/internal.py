"""Internal type definitions for Adaptyv Lab SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FilterStatus(str, Enum):
    """Status after auto-filtering stage."""

    PASSED = "passed"
    FILTERED_BEFORE_SUBMIT = "filtered_before_submit"


class ReviewStatus(str, Enum):
    """Status after manual review stage."""

    PENDING = "pending"
    APPROVED = "approved"
    REVIEWER_DENIED = "reviewer_denied"


class ExperimentStatus(str, Enum):
    """Experiment lifecycle status."""

    DRAFT = "draft"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    CONFIRMED = "confirmed"
    IN_PRODUCTION = "in_production"
    DONE = "done"
    CANCELED = "canceled"


class ResultStatus(str, Enum):
    """Sequence result status for internal experiment lifecycle tracking.

    Use this enum for tracking sequence status through the experiment workflow.
    For BO/AL feedback loops, use FailurePoint from types.results instead.

    Status flow:
        PENDING -> SUBMITTED -> (NO_EXPRESSION | NO_BINDING | BINDING_CONFIRMED | UNKNOWN_BAD)
        PENDING -> REVIEWER_DENIED (if rejected during manual review)
    """

    PENDING = "pending"  # Not yet submitted to Foundry
    SUBMITTED = "submitted"  # Submitted, awaiting results
    NO_EXPRESSION = "no_expression"  # Expressed but didn't produce protein
    NO_BINDING = "no_binding"  # Expressed but didn't bind target
    BINDING_CONFIRMED = "binding_confirmed"  # Success - binding confirmed
    REVIEWER_DENIED = "reviewer_denied"  # Filtered out during human review
    UNKNOWN_BAD = "unknown_bad"  # Failed for unknown/other reason


@dataclass
class DesignMetrics:
    """Computed metrics for a design sequence."""

    plddt: float | None = None
    iptm: float | None = None
    ipsae: float | None = None
    shape_complementarity: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "plddt": self.plddt,
            "iptm": self.iptm,
            "ipsae": self.ipsae,
            "shape_complementarity": self.shape_complementarity,
        }


@dataclass
class CostEstimate:
    """Cost estimates for design pipeline."""

    generation_usd: float
    auto_filtering_usd: float
    manual_filtering_usd: float
    experimental_usd: float  # From Foundry quote

    generation_range: tuple[float, float] = (0.10, 0.50)
    experimental_range: tuple[float, float] = (99.0, 500.0)

    can_upsize: bool = True
    can_downsize: bool = True
    upsize_cost_delta: float = 0.10
    downsize_cost_delta: float = -0.05

    @property
    def total_computational_usd(self) -> float:
        return self.generation_usd + self.auto_filtering_usd + self.manual_filtering_usd

    @property
    def total_usd(self) -> float:
        return self.total_computational_usd + self.experimental_usd


@dataclass
class Target:
    """Target protein for binding experiments."""

    id: str
    name: str
    description: str | None = None
    swissprot_id: str | None = None
    species: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Target:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            swissprot_id=data.get("swissprot_id"),
            species=data.get("species"),
        )


@dataclass
class ExperimentResult:
    """Result from @lab.experiment decorator or API call."""

    experiment_id: str
    experiment_url: str
    status: ExperimentStatus
    cost_estimate: CostEstimate | None = None

    # Populated after confirmation
    confirmed_at: str | None = None

    # Populated when results ready
    results_status: str | None = None  # "none" | "partial" | "all"
    results: dict[str, Any] | None = None

    # Tracking
    sequences_submitted: int = 0
    sequences_passed: int = 0
    sequences_failed: int = 0

    @property
    def is_confirmed(self) -> bool:
        return self.status in (
            ExperimentStatus.CONFIRMED,
            ExperimentStatus.IN_PRODUCTION,
            ExperimentStatus.DONE,
        )

    @property
    def is_complete(self) -> bool:
        return self.status == ExperimentStatus.DONE


@dataclass
class SequenceDesignMetadata:
    """Metadata for a single designed sequence (stored in JSONB)."""

    design_source: str  # "bindcraft" | "germinal" | "manual"
    design_index: int | None = None
    structure_url: str | None = None
    metrics: DesignMetrics | None = None
    filter_status: FilterStatus = FilterStatus.PASSED
    review_status: ReviewStatus = ReviewStatus.PENDING
    experiment_status: ResultStatus = ResultStatus.PENDING
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_source": self.design_source,
            "design_index": self.design_index,
            "structure_url": self.structure_url,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "filter_status": self.filter_status.value,
            "review_status": self.review_status.value,
            "experiment_status": self.experiment_status.value,
            "failure_reason": self.failure_reason,
        }


@dataclass
class DesignWorkflowMetadata:
    """Workflow metadata stored in experiment.data JSONB."""

    workflow_type: str  # "bindcraft" | "germinal"
    workflow_params: dict[str, Any] = field(default_factory=dict)
    modal_job_id: str | None = None
    filter_config: dict[str, Any] = field(default_factory=dict)
    auto_filtered_count: int = 0
    submitted_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_type": self.workflow_type,
            "workflow_params": self.workflow_params,
            "modal_job_id": self.modal_job_id,
            "filter_config": self.filter_config,
            "auto_filtered_count": self.auto_filtered_count,
            "submitted_count": self.submitted_count,
        }


# =============================================================================
# API Cost Estimate Types (Internal API only)
# =============================================================================


@dataclass
class AssayCost:
    """Assay-related costs from API cost estimate.

    All amounts in USD cents.
    """

    experiment_type: str
    sequence_count: int
    n_replicates: int
    unit_price_cents: int
    replicate_price_cents: int
    subtotal_cents: int


@dataclass
class MaterialCost:
    """Material costs for target antigens.

    Present only for binding experiments (screening, affinity).
    All amounts in USD cents.
    """

    target_id: str
    target_name: str
    unit_price_cents: int
    quantity: int
    subtotal_cents: int


@dataclass
class MaterialsUnavailable:
    """Explanation for missing materials pricing."""

    target_id: str
    target_name: str
    reason: str


@dataclass
class APICostBreakdown:
    """Complete cost breakdown from API.

    All amounts in USD cents and exclude VAT.
    """

    pricing_version: str
    assay: AssayCost
    total_cents: int
    materials: MaterialCost | None = None


@dataclass
class APIIncompleteCostEstimate:
    """Partial cost estimate when materials pricing is unavailable."""

    pricing_version: str
    assay: AssayCost
    materials_unavailable: MaterialsUnavailable
    total_cents: int | None = None  # None when materials pricing unavailable


@dataclass
class APICostEstimateResponse:
    """Response from POST /experiments/costestimate.

    Contains either a complete breakdown or an incomplete estimate.
    """

    breakdown: APICostBreakdown | None = None
    incomplete: APIIncompleteCostEstimate | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """True if pricing is fully available."""
        return self.breakdown is not None

    @property
    def total_cents(self) -> int | None:
        """Get total cost in cents, or None if incomplete."""
        if self.breakdown:
            return self.breakdown.total_cents
        return None

    @property
    def assay_subtotal_cents(self) -> int:
        """Get assay subtotal (always available)."""
        if self.breakdown:
            return self.breakdown.assay.subtotal_cents
        if self.incomplete:
            return self.incomplete.assay.subtotal_cents
        return 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> APICostEstimateResponse:
        """Parse API response into structured object."""
        breakdown = None
        incomplete = None
        warnings = data.get("warnings", [])

        if data.get("breakdown"):
            bd = data["breakdown"]
            assay_data = bd["assay"]
            assay = AssayCost(
                experiment_type=assay_data["experiment_type"],
                sequence_count=assay_data["sequence_count"],
                n_replicates=assay_data["n_replicates"],
                unit_price_cents=assay_data["unit_price_cents"],
                replicate_price_cents=assay_data["replicate_price_cents"],
                subtotal_cents=assay_data["subtotal_cents"],
            )

            materials = None
            if bd.get("materials"):
                mat = bd["materials"]
                materials = MaterialCost(
                    target_id=mat["target_id"],
                    target_name=mat["target_name"],
                    unit_price_cents=mat["unit_price_cents"],
                    quantity=mat["quantity"],
                    subtotal_cents=mat["subtotal_cents"],
                )

            breakdown = APICostBreakdown(
                pricing_version=bd["pricing_version"],
                assay=assay,
                total_cents=bd["total_cents"],
                materials=materials,
            )

        if data.get("incomplete"):
            inc = data["incomplete"]
            assay_data = inc["assay"]
            assay = AssayCost(
                experiment_type=assay_data["experiment_type"],
                sequence_count=assay_data["sequence_count"],
                n_replicates=assay_data["n_replicates"],
                unit_price_cents=assay_data["unit_price_cents"],
                replicate_price_cents=assay_data["replicate_price_cents"],
                subtotal_cents=assay_data["subtotal_cents"],
            )

            mat_unavail = inc["materials_unavailable"]
            materials_unavailable = MaterialsUnavailable(
                target_id=mat_unavail["target_id"],
                target_name=mat_unavail["target_name"],
                reason=mat_unavail["reason"],
            )

            incomplete = APIIncompleteCostEstimate(
                pricing_version=inc["pricing_version"],
                assay=assay,
                materials_unavailable=materials_unavailable,
                total_cents=inc.get("total_cents"),
            )

        return cls(
            breakdown=breakdown,
            incomplete=incomplete,
            warnings=warnings,
        )
