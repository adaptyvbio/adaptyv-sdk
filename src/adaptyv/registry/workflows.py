"""Workflow registry for the SDK HTTP service and agent tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

WorkflowStartHandler = Callable[[dict[str, Any]], Any]
WorkflowResumeHandler = Callable[[str], Any]


@dataclass(frozen=True)
class WorkflowSpec:
    """Definition of a workflow in the registry."""

    id: str
    name: str
    description: str
    estimated_duration: str
    start: WorkflowStartHandler
    resume: WorkflowResumeHandler


def _start_design_a_protein(payload: dict[str, Any]) -> Any:
    from adaptyv.workflows.design_a_protein import (
        DesignAProteinConfig,
        DesignAProteinWorkflow,
    )

    if not payload.get("target_pdb"):
        raise ValueError("target_pdb is required")

    config = DesignAProteinConfig(
        hotspots=payload.get("hotspots", []),
        contig_map=payload.get("contig_map", ""),
        chain_lengths=payload.get("chain_lengths", (50, 100)),
        num_samples=payload.get("num_samples", 1),
        temperature=payload.get("temperature", 0.1),
    )
    workflow = DesignAProteinWorkflow(config)
    return workflow.start(
        target_pdb=payload["target_pdb"],
        run_name=payload.get("run_name"),
        resume=payload.get("resume", False),
        resume_run_id=payload.get("resume_run_id"),
        resume_stage=payload.get("resume_stage"),
    )


def _resume_design_a_protein(run_id: str) -> Any:
    from adaptyv.workflows.design_a_protein import DesignAProteinWorkflow

    return DesignAProteinWorkflow().resume(run_id)


def _start_bindcraft(payload: dict[str, Any]) -> Any:
    from adaptyv.workflows.bindcraft import BindCraftConfig, BindCraftWorkflow

    if not payload.get("target_pdb"):
        raise ValueError("target_pdb is required")

    config = BindCraftConfig(
        n_trajectories=payload.get("n_trajectories", 50),
        binder_lengths=payload.get("binder_lengths", [80]),
        number_of_final_designs=payload.get("number_of_final_designs", 50),
        binder_chain=payload.get("binder_chain", "B"),
        target_chain=payload.get("target_chain", "A"),
        hotspots=payload.get("hotspots", []),
    )
    workflow = BindCraftWorkflow(config)
    return workflow.start(
        target_pdb=payload["target_pdb"],
        run_name=payload.get("run_name"),
    )


def _resume_bindcraft(run_id: str) -> Any:
    from adaptyv.workflows.bindcraft import BindCraftWorkflow

    return BindCraftWorkflow().resume(run_id)


def _start_germinal(payload: dict[str, Any]) -> Any:
    from adaptyv.workflows.germinal import GerminalConfig, GerminalWorkflow

    config = GerminalConfig(
        target_name=payload.get("target_name", "pdl1"),
        binder_format=payload.get("binder_format", "vhh"),
        design_mode=payload.get("design_mode", "both"),
        max_trajectories=payload.get("max_trajectories", 10),
        num_seqs=payload.get("num_seqs", 40),
    )
    workflow = GerminalWorkflow(config)
    return workflow.start(run_name=payload.get("run_name"))


def _resume_germinal(run_id: str) -> Any:
    from adaptyv.workflows.germinal import GerminalWorkflow

    return GerminalWorkflow().resume(run_id)


_WORKFLOWS: dict[str, WorkflowSpec] = {
    "design-a-protein": WorkflowSpec(
        id="design-a-protein",
        name="Design-A-Protein",
        description="Fast structure-driven binder design workflow.",
        estimated_duration="~30 minutes",
        start=_start_design_a_protein,
        resume=_resume_design_a_protein,
    ),
    "bindcraft": WorkflowSpec(
        id="bindcraft",
        name="BindCraft",
        description="Trajectory-heavy binder search workflow.",
        estimated_duration="~2 hours",
        start=_start_bindcraft,
        resume=_resume_bindcraft,
    ),
    "germinal": WorkflowSpec(
        id="germinal",
        name="Germinal",
        description="Antibody-focused binder design workflow.",
        estimated_duration="~2 hours",
        start=_start_germinal,
        resume=_resume_germinal,
    ),
}


def list_workflows() -> list[WorkflowSpec]:
    """List all registered workflows."""
    return list(_WORKFLOWS.values())


def get_workflow(workflow_id: str) -> WorkflowSpec | None:
    """Get a workflow by id."""
    return _WORKFLOWS.get(workflow_id)
