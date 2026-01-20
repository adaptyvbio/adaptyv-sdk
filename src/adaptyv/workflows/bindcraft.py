"""BindCraft workflow adapter for Modal with streaming results."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from adaptyv.workflows.common import (
    BaseDesign,
    BaseWorkflowRun,
    DesignStatus,
)

logger = logging.getLogger("adaptyv")


@dataclass
class BindCraftDesign(BaseDesign):
    """A single design from BindCraft.

    Extends BaseDesign with BindCraft-specific fields: kind, spec, created_at.
    """

    kind: str = "parent"  # parent (trajectory) or child (mpnn)
    spec: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"kind": self.kind, "spec": self.spec, "created_at": self.created_at})
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BindCraftDesign:
        """Create BindCraftDesign from design.json data."""
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
class BindCraftRun(BaseWorkflowRun[BindCraftDesign]):
    """A BindCraft run with streaming access to designs.

    Inherits from BaseWorkflowRun for common volume operations.
    """

    design_class = BindCraftDesign
    output_volume: str = "mosaic-bindcraft-out"


@dataclass
class BindCraftConfig:
    """Configuration for BindCraft run."""

    n_trajectories: int = 50
    binder_lengths: list[int] = field(default_factory=lambda: [80])
    number_of_final_designs: int = 50
    binder_chain: str = "B"
    target_chain: str = "A"
    runtime_seed: int | None = None  # None = random
    hotspots: list[str] = field(default_factory=list)  # Residue positions, e.g., ["A50", "A123"]

    # Modal settings (BYO endpoints via env vars)
    modal_app_name: str = field(
        default_factory=lambda: os.environ.get(
            "ADAPTYV_BINDCRAFT_MODAL_APP", "mosaic-bindcraft-streaming"
        )
    )
    modal_function_name: str = field(
        default_factory=lambda: os.environ.get(
            "ADAPTYV_BINDCRAFT_MODAL_FUNC", "run_bindcraft_streaming"
        )
    )
    output_volume: str = field(
        default_factory=lambda: os.environ.get(
            "ADAPTYV_BINDCRAFT_OUTPUT_VOLUME", "mosaic-bindcraft-out"
        )
    )

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.n_trajectories < 1:
            raise ValueError("n_trajectories must be >= 1")
        if not self.binder_lengths:
            raise ValueError("binder_lengths cannot be empty")
        if self.number_of_final_designs < 1:
            raise ValueError("number_of_final_designs must be >= 1")


class BindCraftWorkflow:
    """Adapter for calling BindCraft on Modal with streaming results.

    Usage:
        workflow = BindCraftWorkflow()

        # Start a run (returns immediately)
        run = workflow.start(target_pdb="/path/to/target.pdb")

        # Stream designs as they're generated
        for design in run.iter_designs():
            print(f"New design: {design.sequence[:20]}...")

        # Or get all designs at once
        designs = run.get_designs()
    """

    def __init__(self, config: BindCraftConfig | None = None):
        self.config = config or BindCraftConfig()

    def start(
        self,
        *,
        target_pdb: str,
        target_sequence: str | None = None,
        run_name: str | None = None,
    ) -> BindCraftRun:
        """Start a BindCraft run (non-blocking).

        Args:
            target_pdb: Path to target PDB file
            target_sequence: Optional target sequence
            run_name: Optional human-readable name

        Returns:
            BindCraftRun object for tracking progress and getting results
        """
        import modal

        run_id = str(uuid.uuid4())
        output_path = f"/output/{run_id}"

        # Look up and spawn the Modal function
        fn = modal.Function.from_name(
            self.config.modal_app_name,
            self.config.modal_function_name,
        )

        # Build target_overrides to pass hotspots
        target_overrides: dict[str, Any] = {}
        if self.config.hotspots:
            # Convert hotspots list to comma-separated string (strip chain prefix)
            # e.g., ["A50", "A123"] -> "50,123"
            hotspot_residues = ",".join(
                h.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for h in self.config.hotspots
            )
            target_overrides["target_hotspot_residues"] = hotspot_residues

        # Spawn async (non-blocking)
        # Pass config fields as individual kwargs (Modal function expects these)
        fn.spawn(
            run_id=run_id,
            target_pdb=target_pdb,
            target_sequence=target_sequence or "",
            output_path=output_path,
            # Config params - Modal function accepts these as optional overrides
            n_trajectories=self.config.n_trajectories,
            binder_lengths=self.config.binder_lengths,
            number_of_final_designs=self.config.number_of_final_designs,
            target_overrides=target_overrides,
        )

        return BindCraftRun(
            run_id=run_id,
            output_volume=self.config.output_volume,
            output_path=output_path,
        )

    def resume(self, run_id: str) -> BindCraftRun:
        """Resume tracking an existing run."""
        return BindCraftRun(
            run_id=run_id,
            output_volume=self.config.output_volume,
            output_path=f"/output/{run_id}",
        )
