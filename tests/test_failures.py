"""Tests for failure tracking."""

from adaptyv.results.failures import FailureTracker, SequenceResult
from adaptyv.types.internal import ResultStatus


class TestSequenceResult:
    def test_is_success(self) -> None:
        result = SequenceResult(
            sequence_name="design_0",
            sequence="MVKVGVNG",
            status=ResultStatus.BINDING_CONFIRMED,
        )
        assert result.is_success is True
        assert result.is_failure is False

    def test_is_failure_no_expression(self) -> None:
        result = SequenceResult(
            sequence_name="design_1",
            sequence="MKVLVAG",
            status=ResultStatus.NO_EXPRESSION,
        )
        assert result.is_success is False
        assert result.is_failure is True

    def test_is_failure_no_binding(self) -> None:
        result = SequenceResult(
            sequence_name="design_2",
            sequence="MKFLVAG",
            status=ResultStatus.NO_BINDING,
        )
        assert result.is_success is False
        assert result.is_failure is True

    def test_pending_is_neither(self) -> None:
        result = SequenceResult(
            sequence_name="design_3",
            sequence="MKYLVAG",
            status=ResultStatus.PENDING,
        )
        assert result.is_success is False
        assert result.is_failure is False


class TestFailureTracker:
    def test_add_and_get_result(self) -> None:
        tracker = FailureTracker()
        result = SequenceResult(
            sequence_name="design_0",
            sequence="MVKVGVNG",
            status=ResultStatus.BINDING_CONFIRMED,
        )
        tracker.add_result(result)

        retrieved = tracker.get_result("design_0")
        assert retrieved is not None
        assert retrieved.sequence == "MVKVGVNG"
        assert retrieved.status == ResultStatus.BINDING_CONFIRMED

    def test_add_results_batch(self) -> None:
        tracker = FailureTracker()
        results = [
            SequenceResult("d0", "SEQ0", ResultStatus.BINDING_CONFIRMED),
            SequenceResult("d1", "SEQ1", ResultStatus.NO_BINDING),
            SequenceResult("d2", "SEQ2", ResultStatus.NO_EXPRESSION),
        ]
        tracker.add_results(results)

        assert len(tracker) == 3

    def test_get_sequences_by_status(self) -> None:
        tracker = FailureTracker()
        tracker.add_results(
            [
                SequenceResult("d0", "SEQ0", ResultStatus.BINDING_CONFIRMED),
                SequenceResult("d1", "SEQ1", ResultStatus.BINDING_CONFIRMED),
                SequenceResult("d2", "SEQ2", ResultStatus.NO_BINDING),
                SequenceResult("d3", "SEQ3", ResultStatus.NO_EXPRESSION),
            ]
        )

        binders = tracker.get_sequences_by_status(ResultStatus.BINDING_CONFIRMED)
        assert len(binders) == 2

        no_binding = tracker.get_sequences_by_status(ResultStatus.NO_BINDING)
        assert len(no_binding) == 1

    def test_get_stats(self) -> None:
        tracker = FailureTracker()
        tracker.add_results(
            [
                SequenceResult("d0", "SEQ0", ResultStatus.BINDING_CONFIRMED),
                SequenceResult("d1", "SEQ1", ResultStatus.BINDING_CONFIRMED),
                SequenceResult("d2", "SEQ2", ResultStatus.NO_BINDING),
                SequenceResult("d3", "SEQ3", ResultStatus.NO_EXPRESSION),
                SequenceResult("d4", "SEQ4", ResultStatus.UNKNOWN_BAD),
            ]
        )

        stats = tracker.get_stats()
        assert stats.total_sequences == 5
        assert stats.binding_confirmed == 2
        assert stats.no_binding == 1
        assert stats.no_expression == 1
        assert stats.unknown_bad == 1
        assert stats.pending == 0

    def test_success_rate(self) -> None:
        tracker = FailureTracker()
        tracker.add_results(
            [
                SequenceResult("d0", "SEQ0", ResultStatus.BINDING_CONFIRMED),
                SequenceResult("d1", "SEQ1", ResultStatus.NO_BINDING),
                SequenceResult("d2", "SEQ2", ResultStatus.NO_BINDING),
                SequenceResult("d3", "SEQ3", ResultStatus.NO_BINDING),
            ]
        )

        stats = tracker.get_stats()
        assert stats.success_rate == 0.25  # 1/4

    def test_expression_rate(self) -> None:
        tracker = FailureTracker()
        tracker.add_results(
            [
                SequenceResult("d0", "SEQ0", ResultStatus.BINDING_CONFIRMED),
                SequenceResult("d1", "SEQ1", ResultStatus.NO_BINDING),
                SequenceResult("d2", "SEQ2", ResultStatus.NO_EXPRESSION),
                SequenceResult("d3", "SEQ3", ResultStatus.NO_EXPRESSION),
            ]
        )

        stats = tracker.get_stats()
        assert stats.expression_rate == 0.5  # 2/4 expressed

    def test_to_active_learning_feedback(self) -> None:
        tracker = FailureTracker()
        tracker.add_results(
            [
                SequenceResult("d0", "SEQ0", ResultStatus.BINDING_CONFIRMED, kd_value=1e-9),
                SequenceResult("d1", "SEQ1", ResultStatus.NO_BINDING, kd_value=1e-5),
                SequenceResult("d2", "SEQ2", ResultStatus.NO_EXPRESSION),
                SequenceResult("d3", "SEQ3", ResultStatus.UNKNOWN_BAD),
            ]
        )

        feedback = tracker.to_active_learning_feedback()

        assert len(feedback["positives"]) == 1
        assert feedback["positives"][0]["sequence"] == "SEQ0"
        assert feedback["positives"][0]["kd_value"] == 1e-9

        assert len(feedback["negatives"]) == 1
        assert feedback["negatives"][0]["sequence"] == "SEQ1"

        assert len(feedback["hard_negatives"]) == 1
        assert feedback["hard_negatives"][0]["sequence"] == "SEQ2"

        assert len(feedback["excluded"]) == 1
        assert feedback["excluded"][0]["sequence"] == "SEQ3"

    def test_clear(self) -> None:
        tracker = FailureTracker()
        tracker.add_result(SequenceResult("d0", "SEQ0", ResultStatus.BINDING_CONFIRMED))
        assert len(tracker) == 1

        tracker.clear()
        assert len(tracker) == 0

    def test_empty_stats(self) -> None:
        tracker = FailureTracker()
        stats = tracker.get_stats()

        assert stats.total_sequences == 0
        assert stats.success_rate == 0.0
        assert stats.expression_rate == 0.0
