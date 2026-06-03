"""Internal type definitions for Adaptyv SDK."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adaptyv.types.generated import ExperimentStatus, ResultsStatus


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

    # Populated after confirmation
    confirmed_at: str | None = None

    # Populated when results ready
    results_status: ResultsStatus | None = None
    results: dict[str, Any] | None = None

    # Tracking
    sequences_submitted: int = 0
    sequences_passed: int = 0
    sequences_failed: int = 0

    @property
    def is_confirmed(self) -> bool:
        """True if experiment is confirmed (past waiting_for_confirmation stage)."""
        return self.status in (
            ExperimentStatus.waiting_for_materials,
            ExperimentStatus.in_production,
            ExperimentStatus.in_queue,
            ExperimentStatus.data_analysis,
            ExperimentStatus.in_review,
            ExperimentStatus.done,
        )

    @property
    def is_complete(self) -> bool:
        return self.status == ExperimentStatus.done
