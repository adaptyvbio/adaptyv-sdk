"""Design-A-Protein workflow adapter using Modal with streaming results.

This adapter spawns the proteindesign-demo Modal app which orchestrates
Protpardelle (structure generation) and LigandMPNN (sequence design) with
volume-based streaming output.

Two-phase pipeline (orchestrated by Modal app):
  Phase 1: Structure Generation (Protpardelle)
    - Input: target PDB, hotspots, contig_map, chain_lengths, num_samples
    - Output: PDB URLs with shape_complementarity scores

  Phase 2: Sequence Design (LigandMPNN)
    - Input: PDB structures, temperature
    - Output: Amino acid sequences with mpnn_score
"""

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
class DesignAProteinDesign(BaseDesign):
    """A single design from the Design-A-Protein pipeline.

    Uses BaseDesign fields directly with no extra fields.
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DesignAProteinDesign:
        """Create DesignAProteinDesign from dict data."""
        return cls(
            design_id=data.get("design_id", ""),
            sequence=data.get("sequence", ""),
            structure_path=data.get("structure_path"),
            metrics=data.get("metrics", {}),
            status=data.get("status", DesignStatus.PENDING.value),
        )


@dataclass
class DesignAProteinConfig:
    """Configuration for Design-A-Protein run.

    Structure generation params (Protpardelle):
        hotspots: Residue positions to target, e.g., ["A50", "A123", "A205"]
        contig_map: Chain mapping string, e.g., "A1-413"
        chain_lengths: (min, max) binder length, e.g., (50, 150)
        num_samples: Number of structures to generate (1-20)

    Sequence design params (LigandMPNN):
        temperature: Sampling temperature (0.05-0.5, lower = more confident)

    Modal config:
        modal_app_name: Modal app name for streaming orchestrator
        modal_function_name: Modal function name
        output_volume: Modal volume for output
    """

    # Structure params
    hotspots: list[str] = field(default_factory=list)
    contig_map: str = ""
    chain_lengths: tuple[int, int] = (50, 100)
    num_samples: int = 1

    # Sequence params
    temperature: float = 0.1

    # Model params (Protpardelle) - matches proteindesign-demo defaults
    model: tuple[str, str, str] = ("cc83", "2616", "sampling_sidechain_conditional")
    step_scales: list[float] = field(default_factory=lambda: [1.2])
    schurns: list[float] = field(default_factory=lambda: [1.0])
    crop_cond_starts: list[float] = field(default_factory=lambda: [0.0])
    translations: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Batch size (GPU memory constraint)
    batch_size: int = 2

    # Modal config - streaming orchestrator (BYO endpoints via env vars)
    modal_app_name: str = field(
        default_factory=lambda: os.environ.get("ADAPTYV_DAP_MODAL_APP", "proteindesign-demo")
    )
    modal_function_name: str = field(
        default_factory=lambda: os.environ.get("ADAPTYV_DAP_MODAL_FUNC", "run_dap_streaming")
    )
    output_volume: str = field(
        default_factory=lambda: os.environ.get("ADAPTYV_DAP_OUTPUT_VOLUME", "proteindesign-demo")
    )

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.num_samples < 1:
            raise ValueError("num_samples must be >= 1")
        if self.batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if len(self.chain_lengths) != 2:
            raise ValueError("chain_lengths must be a tuple of (min, max)")
        if self.chain_lengths[0] > self.chain_lengths[1]:
            raise ValueError("chain_lengths[0] must be <= chain_lengths[1]")
        if self.temperature <= 0:
            raise ValueError("temperature must be > 0")


@dataclass
class DesignAProteinRun(BaseWorkflowRun[DesignAProteinDesign]):
    """A Design-A-Protein run with streaming access to designs.

    Inherits from BaseWorkflowRun for common volume operations.
    Uses config.output_volume for the Modal volume name.

    Usage:
        run = workflow.start(...)

        # Get current status
        status = run.get_status()

        # Poll for all designs (blocking)
        designs = run.get_designs()

        # Or stream as they complete
        for design in run.iter_designs():
            print(f"Got: {design.design_id}")
    """

    design_class = DesignAProteinDesign
    output_volume: str = "proteindesign-demo"  # Default, can be overridden by config
    config: DesignAProteinConfig = field(default_factory=DesignAProteinConfig)

    def _get_volume(self) -> Any:
        """Get cached Modal volume handle using config.output_volume."""
        if self._volume is None:
            import modal

            self._volume = modal.Volume.from_name(self.config.output_volume)
        return self._volume


class DesignAProteinWorkflow:
    """Adapter for Design-A-Protein pipeline via Modal with streaming results.

    Usage:
        config = DesignAProteinConfig(
            hotspots=["A50", "A123"],
            contig_map="A1-413",
            chain_lengths=(80, 120),
            num_samples=5,
            temperature=0.1,
        )

        workflow = DesignAProteinWorkflow(config)

        # Start a run (non-blocking, spawns Modal job)
        run = workflow.start(target_pdb="https://files.rcsb.org/view/2VSM.pdb")

        # Stream designs as they complete
        for design in run.iter_designs():
            print(f"New design: {design.sequence[:20]}...")
            print(f"Metrics: {design.metrics}")

        # Or get all at once
        designs = run.get_designs()
    """

    def __init__(self, config: DesignAProteinConfig | None = None):
        self.config = config or DesignAProteinConfig()

    def start(
        self,
        *,
        target_pdb: str,
        run_name: str | None = None,
        resume: bool = False,
        resume_run_id: str | None = None,
        resume_stage: str | None = None,
    ) -> DesignAProteinRun:
        """Start a Design-A-Protein run (non-blocking).

        Args:
            target_pdb: URL to target PDB file
            run_name: Optional human-readable name for the run
            resume: Resume a prior run_id instead of creating a new one
            resume_run_id: Existing run_id to resume (when resume=True)
            resume_stage: Optional stage hint (structures/sequences)

        Returns:
            DesignAProteinRun object for tracking progress and getting results
        """
        import modal

        run_id = resume_run_id if resume and resume_run_id else str(uuid.uuid4())
        output_path = f"/output/{run_id}"

        # Look up and spawn the Modal function
        fn = modal.Function.from_name(
            self.config.modal_app_name,
            self.config.modal_function_name,
        )

        # Spawn async (non-blocking)
        spawn_kwargs: dict[str, Any] = {
            "run_id": run_id,
            "output_path": output_path,
            "target_pdb_url": target_pdb,
            "hotspots": self.config.hotspots,
            "contig_map": self.config.contig_map,
            "chain_lengths": self.config.chain_lengths,
            "num_samples": self.config.num_samples,
            "temperature": self.config.temperature,
            "model": self.config.model,
            "step_scales": self.config.step_scales,
            "schurns": self.config.schurns,
            "crop_cond_starts": self.config.crop_cond_starts,
            "translations": self.config.translations,
            "batch_size": self.config.batch_size,
        }
        if resume:
            spawn_kwargs["resume"] = True
            if resume_stage:
                spawn_kwargs["resume_stage"] = resume_stage

        fn.spawn(**spawn_kwargs)

        return DesignAProteinRun(
            run_id=run_id,
            output_path=output_path,
            config=self.config,
        )

    def resume(self, run_id: str) -> DesignAProteinRun:
        """Resume tracking an existing run from Modal volume.

        Args:
            run_id: The run ID to resume

        Returns:
            DesignAProteinRun object for tracking the existing run
        """
        output_path = f"/output/{run_id}"
        return DesignAProteinRun(
            run_id=run_id,
            output_path=output_path,
            config=self.config,
        )
