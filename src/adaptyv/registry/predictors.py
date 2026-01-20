"""Predictor registry for the SDK HTTP service and agent tools."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from adaptyv.predictors.plm_sol import predict_solubility as predict_solubility_plm_sol
from adaptyv.predictors.rp3net import predict_expression_rp3net

logger = logging.getLogger(__name__)

PredictorRunHandler = Callable[["PredictorRunData"], Awaitable["PredictorRunResult"]]


@dataclass(frozen=True)
class PredictorRunData:
    """Input payload for predictor runs."""

    design_run_id: str
    design_ids: list[str]
    sequences: dict[str, str]
    params: dict[str, Any]


@dataclass(frozen=True)
class PredictorResult:
    """Single predictor result for a design."""

    design_id: str
    metrics: dict[str, Any]
    structure_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_id": self.design_id,
            "metrics": self.metrics,
            "structure_url": self.structure_url,
        }


@dataclass(frozen=True)
class PredictorRunResult:
    """Result payload for predictor runs."""

    status: str
    results: list[PredictorResult]
    error: str | None = None


@dataclass(frozen=True)
class PredictorSpec:
    """Definition of a predictor in the registry."""

    id: str
    name: str
    description: str
    endpoint_url: str
    input_types: list[str]
    output_metrics: list[str]
    compute_requirements: dict[str, Any]
    run: PredictorRunHandler


async def _run_solubility(request: PredictorRunData) -> PredictorRunResult:
    """Run solubility/expression predictions using multiple models.

    Supports:
    - PLM_Sol (solubility prediction)
    - RP3Net (expression prediction)

    The `params` dict can specify which models to run:
    - params.get("models", ["plm_sol", "rp3net"]) - list of models to run
    - If not specified, runs all available models
    """
    if not request.design_ids or not request.sequences:
        return PredictorRunResult(
            status="failed",
            results=[],
            error="No sequences provided for prediction.",
        )

    # Determine which models to run
    models_to_run = request.params.get("models", ["plm_sol", "rp3net"])
    if isinstance(models_to_run, str):
        models_to_run = [models_to_run]

    # Normalize model names
    models_to_run = [m.lower().strip() for m in models_to_run]

    results: list[PredictorResult] = []
    errors: list[str] = []

    # Run predictions for each design
    for design_id in request.design_ids:
        sequence = request.sequences.get(design_id)
        if not sequence:
            continue

        metrics: dict[str, Any] = {}

        # Run PLM_Sol if requested
        if "plm_sol" in models_to_run:
            try:
                plm_result = await predict_solubility_plm_sol(sequence)
                metrics["plm_sol_solubility_score"] = plm_result.solubility_score
            except Exception as e:
                errors.append(f"PLM_Sol failed for {design_id}: {e}")

        # Run RP3Net if requested
        if "rp3net" in models_to_run:
            try:
                rp3net_result = await predict_expression_rp3net(sequence)
                metrics["rp3net_expression_score"] = rp3net_result.expression_score
            except Exception as e:
                errors.append(f"RP3Net failed for {design_id}: {e}")

        # Add combined solubility score (from PLM_Sol)
        if "plm_sol_solubility_score" in metrics:
            metrics["solubility_score"] = metrics["plm_sol_solubility_score"]

        # Add combined expression score (from RP3Net)
        if "rp3net_expression_score" in metrics:
            metrics["expression_prediction"] = metrics["rp3net_expression_score"]

        if metrics:
            results.append(
                PredictorResult(
                    design_id=design_id,
                    metrics=metrics,
                )
            )

    if not results:
        return PredictorRunResult(
            status="failed",
            results=[],
            error=f"All predictions failed. Errors: {'; '.join(errors)}"
            if errors
            else "No predictions generated.",
        )

    # Return partial success if some failed
    status = "completed" if not errors else "partial"

    return PredictorRunResult(
        status=status,
        results=results,
        error="; ".join(errors) if errors else None,
    )


_PREDICTORS: dict[str, PredictorSpec] = {
    "solubility": PredictorSpec(
        id="solubility",
        name="Solubility & Expression Predictor",
        description="Predicts protein solubility and expression using PLM_Sol and RP3Net. Use params.models to specify which models to run (default: all).",
        endpoint_url="internal",  # Internal routing, not direct endpoint
        input_types=["sequence"],
        output_metrics=[
            "solubility_score",
            "expression_prediction",
            "plm_sol_solubility_score",
            "rp3net_expression_score",
        ],
        compute_requirements={"gpu": False, "estimated_time_per_sequence": 15},
        run=_run_solubility,
    )
}


def list_predictors() -> list[PredictorSpec]:
    """List all registered predictors."""
    return list(_PREDICTORS.values())


def get_predictor(predictor_id: str) -> PredictorSpec | None:
    """Get a predictor by id."""
    return _PREDICTORS.get(predictor_id)


def list_predictor_ids() -> list[str]:
    """List available predictor ids."""
    return list(_PREDICTORS.keys())


def predictor_info(spec: PredictorSpec) -> dict[str, Any]:
    """Build predictor metadata for HTTP responses."""
    return {
        "id": spec.id,
        "name": spec.name,
        "description": spec.description,
        "endpoint_url": spec.endpoint_url,
        "input_types": spec.input_types,
        "output_metrics": spec.output_metrics,
        "compute_requirements": spec.compute_requirements,
    }
