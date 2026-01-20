"""Failure tracking for active learning feedback loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from adaptyv.types.internal import ResultStatus


@dataclass
class SequenceResult:
    """Result for a single sequence in an experiment."""

    sequence_name: str
    sequence: str
    status: ResultStatus
    kd_value: float | None = None  # Dissociation constant if measured
    expression_level: float | None = None
    failure_reason: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == ResultStatus.BINDING_CONFIRMED

    @property
    def is_failure(self) -> bool:
        return self.status in (
            ResultStatus.NO_EXPRESSION,
            ResultStatus.NO_BINDING,
            ResultStatus.REVIEWER_DENIED,
            ResultStatus.UNKNOWN_BAD,
        )


@dataclass
class FailureStats:
    """Aggregated failure statistics for an experiment."""

    total_sequences: int = 0
    binding_confirmed: int = 0
    no_expression: int = 0
    no_binding: int = 0
    reviewer_denied: int = 0
    unknown_bad: int = 0
    pending: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_sequences == 0:
            return 0.0
        return self.binding_confirmed / self.total_sequences

    @property
    def expression_rate(self) -> float:
        """Rate of sequences that expressed (regardless of binding)."""
        if self.total_sequences == 0:
            return 0.0
        expressed = self.total_sequences - self.no_expression - self.pending
        return expressed / self.total_sequences


class FailureTracker:
    """Tracks per-sequence failures for active learning.

    Usage:
        tracker = FailureTracker()

        # Add results from experiment
        tracker.add_result(SequenceResult(
            sequence_name="design_0",
            sequence="MVKVGVNG...",
            status=ResultStatus.BINDING_CONFIRMED,
            kd_value=1.2e-9,
        ))

        # Get stats
        stats = tracker.get_stats()
        print(f"Success rate: {stats.success_rate:.1%}")

        # Get sequences by outcome for AL
        failures = tracker.get_sequences_by_status(ResultStatus.NO_BINDING)
    """

    def __init__(self) -> None:
        self._results: dict[str, SequenceResult] = {}

    def add_result(self, result: SequenceResult) -> None:
        """Add or update a sequence result."""
        self._results[result.sequence_name] = result

    def add_results(self, results: list[SequenceResult]) -> None:
        """Add multiple results."""
        for result in results:
            self.add_result(result)

    def get_result(self, sequence_name: str) -> SequenceResult | None:
        """Get result for a specific sequence."""
        return self._results.get(sequence_name)

    def get_all_results(self) -> list[SequenceResult]:
        """Get all results."""
        return list(self._results.values())

    def get_sequences_by_status(self, status: ResultStatus) -> list[SequenceResult]:
        """Get all sequences with a specific status."""
        return [r for r in self._results.values() if r.status == status]

    def get_stats(self) -> FailureStats:
        """Get aggregated failure statistics."""
        stats = FailureStats(total_sequences=len(self._results))

        for result in self._results.values():
            if result.status == ResultStatus.BINDING_CONFIRMED:
                stats.binding_confirmed += 1
            elif result.status == ResultStatus.NO_EXPRESSION:
                stats.no_expression += 1
            elif result.status == ResultStatus.NO_BINDING:
                stats.no_binding += 1
            elif result.status == ResultStatus.REVIEWER_DENIED:
                stats.reviewer_denied += 1
            elif result.status == ResultStatus.UNKNOWN_BAD:
                stats.unknown_bad += 1
            else:
                stats.pending += 1

        return stats

    def to_active_learning_feedback(self) -> dict[str, Any]:
        """Export results in format suitable for active learning.

        Returns dict with:
            - positives: sequences with confirmed binding (with KD)
            - hard_negatives: no_expression sequences
            - negatives: no_binding sequences (with KD if available)
            - excluded: unknown_bad + reviewer_denied sequences
        """
        excluded_statuses = [ResultStatus.UNKNOWN_BAD, ResultStatus.REVIEWER_DENIED]
        return {
            "positives": [
                {
                    "sequence": r.sequence,
                    "kd_value": r.kd_value,
                    "name": r.sequence_name,
                }
                for r in self.get_sequences_by_status(ResultStatus.BINDING_CONFIRMED)
            ],
            "hard_negatives": [
                {"sequence": r.sequence, "name": r.sequence_name}
                for r in self.get_sequences_by_status(ResultStatus.NO_EXPRESSION)
            ],
            "negatives": [
                {
                    "sequence": r.sequence,
                    "kd_value": r.kd_value,
                    "name": r.sequence_name,
                }
                for r in self.get_sequences_by_status(ResultStatus.NO_BINDING)
            ],
            "excluded": [
                {"sequence": r.sequence, "name": r.sequence_name}
                for status in excluded_statuses
                for r in self.get_sequences_by_status(status)
            ],
        }

    def clear(self) -> None:
        """Clear all results."""
        self._results.clear()

    def __len__(self) -> int:
        """Return number of tracked results."""
        return len(self._results)
