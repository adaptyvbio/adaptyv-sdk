"""Germinal workflow adapter for Modal with streaming results.

Germinal is an antibody/VHH design workflow using AlphaFold2 with specialized losses.
It supports VHH (nanobody) and scFv (single-chain Fv) binder formats.

Two-tier API:
  - Simple: GerminalConfig with target_name, binder_format, design_mode, max_trajectories
  - Advanced: GerminalAdvancedConfig for optimization steps, loss weights, filter thresholds
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

from adaptyv.workflows.common import (
    BaseDesign,
    BaseWorkflowRun,
    DesignStatus,
)

logger = logging.getLogger("adaptyv")


@dataclass
class GerminalDesign(BaseDesign):
    """A single design from Germinal.

    Extends BaseDesign with Germinal-specific fields: kind, spec, created_at.
    VHH designs include CDR-specific metrics and germline humanization scores.
    """

    kind: str = "parent"  # parent (trajectory) or child (abmpnn)
    spec: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"kind": self.kind, "spec": self.spec, "created_at": self.created_at})
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GerminalDesign:
        """Create GerminalDesign from design.json data."""
        return cls(
            design_id=data.get("design_id", ""),
            sequence=data.get("sequence", ""),
            structure_path=data.get("structure_path"),
            metrics=data.get("metrics", {}),
            status=data.get("status", DesignStatus.PENDING.value),
            kind=data.get("kind", "parent"),
            spec=data.get("spec", {}),
            created_at=data.get("created_at"),
        )


@dataclass
class GerminalAdvancedConfig:
    """Advanced configuration for power users.

    Controls optimization steps, loss weights, filter thresholds, and backend.
    """

    # Optimization steps
    logits_steps: int = 65
    softmax_steps: int = 35
    search_steps: int = 10

    # Loss weights
    weights_plddt: float = 1.0
    weights_iptm: float = 0.75
    weights_pae_inter: float = 0.5
    weights_con_intra: float = 0.1
    weights_con_inter: float = 0.2
    weights_rg: float = 0.1
    weights_helix: float = 0.1
    weights_beta: float = 0.2

    # Filter thresholds
    plddt_threshold: float = 0.82
    i_ptm_threshold: float = 0.68
    i_pae_threshold: float = 0.27

    # Backend and filter control
    backend: str = "freebindcraft"  # "freebindcraft" or "pyrosetta"
    no_initial_filters: bool = False
    no_final_filters: bool = False


@dataclass
class GerminalConfig:
    """Configuration for Germinal run.

    Simple config params (most users):
        target_name: Target name (MVP: only "pdl1" supported)
        binder_format: "vhh" (nanobody) or "scfv" (single-chain Fv)
        design_mode: "both" (template + IgLM), "template", or "iglm"
        max_trajectories: Number of parent trajectories to run
        num_seqs: AbMPNN sequences per trajectory

    Advanced config (power users):
        advanced: GerminalAdvancedConfig for fine-grained control
    """

    # Simple config
    target_name: str = "pdl1"  # MVP: only pdl1 supported
    binder_format: str = "vhh"  # "vhh" or "scfv"
    design_mode: str = "both"  # "both", "template", "iglm"
    max_trajectories: int = 10
    num_seqs: int = 40  # AbMPNN sequences per trajectory

    # Advanced config (optional)
    advanced: GerminalAdvancedConfig | None = None

    # Modal settings (BYO endpoints via env vars)
    modal_app_name: str = field(
        default_factory=lambda: os.environ.get(
            "ADAPTYV_GERMINAL_MODAL_APP", "mosaic-germinal-streaming"
        )
    )
    modal_function_name: str = field(
        default_factory=lambda: os.environ.get(
            "ADAPTYV_GERMINAL_MODAL_FUNC", "run_germinal_streaming"
        )
    )
    output_volume: str = field(
        default_factory=lambda: os.environ.get("ADAPTYV_GERMINAL_OUTPUT_VOLUME", "mosaic-outputs")
    )

    def __post_init__(self) -> None:
        """Validate config values."""
        # MVP: only pdl1 supported
        if self.target_name != "pdl1":
            raise ValueError(f"target_name must be 'pdl1' (MVP). Got: {self.target_name}")

        if self.binder_format not in ("vhh", "scfv"):
            raise ValueError(f"binder_format must be 'vhh' or 'scfv'. Got: {self.binder_format}")

        if self.design_mode not in ("both", "template", "iglm"):
            raise ValueError(
                f"design_mode must be 'both', 'template', or 'iglm'. Got: {self.design_mode}"
            )

        if self.max_trajectories < 1:
            raise ValueError(f"max_trajectories must be >= 1. Got: {self.max_trajectories}")


@dataclass
class GerminalRun(BaseWorkflowRun[GerminalDesign]):
    """A Germinal run with streaming access to designs.

    Inherits from BaseWorkflowRun for common volume operations.
    Uses a 30-second poll interval since Germinal runs are slower.

    Usage:
        run = workflow.start(...)

        # Poll for all designs
        designs = run.get_designs()

        # Or stream as they complete
        for design in run.iter_designs():
            print(f"Got: {design.design_id}")
    """

    design_class = GerminalDesign
    default_poll_interval: ClassVar[float] = 30.0  # Germinal is slower
    output_volume: str = "mosaic-outputs"


class GerminalWorkflow:
    """Adapter for calling Germinal on Modal with streaming results.

    Usage:
        workflow = GerminalWorkflow()

        # Start a run (returns immediately)
        run = workflow.start()

        # Stream designs as they're generated
        for design in run.iter_designs():
            print(f"New design: {design.sequence[:20]}...")

        # Or get all designs at once
        designs = run.get_designs()
    """

    def __init__(self, config: GerminalConfig | None = None):
        self.config = config or GerminalConfig()

    def start(self, *, run_name: str | None = None) -> GerminalRun:
        """Start a Germinal run (non-blocking).

        Args:
            run_name: Optional human-readable name

        Returns:
            GerminalRun object for tracking progress and getting results
        """
        import modal

        run_id = str(uuid.uuid4())
        output_path = f"/output/{run_id}"

        # Look up and spawn the Modal function
        fn = modal.Function.from_name(
            self.config.modal_app_name,
            self.config.modal_function_name,
        )

        # Get backend and filter settings from advanced config
        backend = "freebindcraft"
        no_initial_filters = False
        no_final_filters = False
        if self.config.advanced:
            backend = self.config.advanced.backend
            no_initial_filters = self.config.advanced.no_initial_filters
            no_final_filters = self.config.advanced.no_final_filters

        # Spawn async (non-blocking)
        # Pass config fields as individual kwargs (Modal function expects these)
        fn.spawn(
            run_id=run_id,
            output_path=output_path,
            target_name=self.config.target_name,
            binder_format=self.config.binder_format,
            design_mode=self.config.design_mode,
            max_trajectories=self.config.max_trajectories,
            backend=backend,
            no_initial_filters=no_initial_filters,
            no_final_filters=no_final_filters,
        )

        return GerminalRun(
            run_id=run_id,
            output_volume=self.config.output_volume,
            output_path=output_path,
        )

    def resume(self, run_id: str) -> GerminalRun:
        """Resume tracking an existing run."""
        return GerminalRun(
            run_id=run_id,
            output_volume=self.config.output_volume,
            output_path=f"/output/{run_id}",
        )
