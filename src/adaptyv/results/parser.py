"""Parse Adaptyv data package zip files."""

from __future__ import annotations

import csv
import logging
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from adaptyv.results.failures import SequenceResult
from adaptyv.types.internal import ResultStatus

logger = logging.getLogger(__name__)


def parse_data_package(zip_path: str | Path) -> list[SequenceResult]:
    """Parse a data package zip into SequenceResult objects.

    Args:
        zip_path: Path to data package zip downloaded from Foundry Portal

    Returns:
        List of SequenceResult objects (one per unique sequence, aggregated across replicates)

    Example:
        results = parse_data_package("~/Downloads/Germinal_IL3_data_package.zip")
        tracker = FailureTracker()
        tracker.add_results(results)
        feedback = tracker.to_active_learning_feedback()
    """
    zip_path = Path(zip_path).expanduser()

    with zipfile.ZipFile(zip_path, "r") as zf:
        rows = _find_and_parse_summary_csv(zf)

    # Group by sequence name, aggregate replicates
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["name"]].append(row)

    return [_build_sequence_result(name, reps) for name, reps in grouped.items()]


def _find_and_parse_summary_csv(zf: zipfile.ZipFile) -> list[dict[str, Any]]:
    """Find and parse the *_summary.csv file in the zip."""
    for name in zf.namelist():
        if name.endswith("_summary.csv") and "/" not in name:
            with zf.open(name) as f:
                content = f.read().decode("utf-8-sig")  # Handle BOM
                reader = csv.DictReader(content.splitlines())
                return list(reader)
    raise ValueError("No *_summary.csv found in data package")


def _build_sequence_result(name: str, replicates: list[dict[str, Any]]) -> SequenceResult:
    """Build SequenceResult from replicate rows."""
    # Aggregate across replicates
    kd_values = []
    binding_values = []
    expression_values = []

    for rep in replicates:
        # Parse kd (may be "null" string)
        kd_str = rep.get("kd", "null")
        if kd_str and kd_str != "null":
            try:
                kd_values.append(float(kd_str))
            except ValueError as e:
                logger.debug("Could not parse kd value '%s': %s", kd_str, e)

        binding_values.append(rep.get("binding", "unknown"))
        expression_values.append(rep.get("expression", "none"))

    # Determine status from binding + expression
    status = _determine_status(binding_values, expression_values)

    # Get sequence from first replicate (same across all)
    sequence = replicates[0].get("sequence", "")

    return SequenceResult(
        sequence_name=name,
        sequence=sequence,
        status=status,
        kd_value=sum(kd_values) / len(kd_values) if kd_values else None,
        expression_level=_expression_to_float(expression_values),
        raw_data={
            "replicates": replicates,
            "kd_values": kd_values,
            "binding_strength": replicates[0].get("binding_strength"),
            "confidence": replicates[0].get("confidence"),
            "method": replicates[0].get("method"),
        },
    )


def _determine_status(binding_values: list[str], expression_values: list[str]) -> ResultStatus:
    """Map binding/expression to ResultStatus."""
    # Check expression first
    if all(e == "none" for e in expression_values):
        return ResultStatus.NO_EXPRESSION

    # Check binding
    if any(b == "true" for b in binding_values):
        return ResultStatus.BINDING_CONFIRMED
    if all(b == "false" for b in binding_values):
        return ResultStatus.NO_BINDING
    if all(b == "unknown" for b in binding_values):
        return ResultStatus.UNKNOWN_BAD

    # Mixed results - conservative: no binding
    return ResultStatus.NO_BINDING


def _expression_to_float(expression_values: list[str]) -> float | None:
    """Convert expression strings to numeric (for aggregation)."""
    mapping = {"high": 1.0, "medium": 0.5, "none": 0.0}
    values = [mapping.get(e, 0.0) for e in expression_values]
    return sum(values) / len(values) if values else None
