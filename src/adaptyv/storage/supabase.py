"""Supabase storage adapter for persisting designs to ProteinRoom.

This module connects the SDK's design generation workflows to the ProteinRoom
UI by inserting designs into the `design_run_sequences` table.

Usage:
    from adaptyv.storage import SupabaseStorage
    from adaptyv.workflows import DesignAProteinWorkflow

    # Setup
    storage = SupabaseStorage(
        url=os.environ["SUPABASE_URL"],
        key=os.environ["SUPABASE_SERVICE_KEY"],
        schema="public",  # Database schema name
    )

    # Generate designs
    workflow = DesignAProteinWorkflow(config)
    run = workflow.start()
    designs = run.get_designs()

    # Persist to Supabase for ProteinRoom review
    ids = storage.save_designs(designs, design_run_id="run-123")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adaptyv.workflows.design_a_protein import DesignAProteinDesign


@dataclass
class SupabaseConfig:
    """Configuration for Supabase connection."""

    url: str
    key: str
    schema: str = "public"  # Database schema name


class SupabaseStorage:
    """Storage adapter for persisting designs to Supabase.

    Connects the SDK's design workflows to ProteinRoom by inserting designs
    into the `design_run_sequences` table for manual review.

    Args:
        url: Supabase project URL (e.g., https://xxx.supabase.co)
        key: Supabase service role key (bypasses RLS)
        schema: Database schema name (default: "public")

    Example:
        storage = SupabaseStorage(
            url=os.environ["SUPABASE_URL"],
            key=os.environ["SUPABASE_SERVICE_KEY"],
        )

        # Save designs from a workflow run
        ids = storage.save_designs(designs, design_run_id="run-123")

        # Query approved designs
        approved = storage.get_approved_designs(design_run_id="run-123")
    """

    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
        schema: str = "public",
    ):
        # Try environment variables if not provided
        self.url = url or os.environ.get("SUPABASE_URL", "")
        self.key = key or os.environ.get("SUPABASE_SERVICE_KEY", "")
        self.schema = schema

        if not self.url or not self.key:
            raise ValueError(
                "Supabase URL and key required. Set SUPABASE_URL and SUPABASE_SERVICE_KEY "
                "environment variables or pass url/key to constructor."
            )

        # Lazy import to avoid requiring supabase for users who don't need storage
        try:
            from supabase import create_client
        except ImportError as e:
            raise ImportError(
                "supabase package required for SupabaseStorage. Install with: pip install supabase"
            ) from e

        self._client = create_client(self.url, self.key)

    def _table(self, name: str) -> Any:
        """Get a table reference in the configured schema."""
        return self._client.schema(self.schema).table(name)

    def save_designs(
        self,
        designs: list[DesignAProteinDesign],
        design_run_id: str,
        batch_name: str | None = None,
    ) -> list[str]:
        """Insert designs into design_run_sequences for ProteinRoom review.

        Args:
            designs: List of designs from a workflow run
            design_run_id: Required foreign key to design_runs table
            batch_name: Optional name prefix for designs

        Returns:
            List of inserted design IDs (UUIDs from Supabase)
        """
        if not designs:
            return []

        rows = []
        for i, design in enumerate(designs):
            design_id = design.design_id
            if batch_name:
                design_id = f"{batch_name}_{i:03d}"

            # Map workflow metrics to ProteinRoom schema
            metrics = {
                "plddt": design.metrics.get("plddt", 0),
                "ipae": design.metrics.get("ipae", 0),
                "iptm": design.metrics.get("iptm", 0),
                "shape_complementarity": design.metrics.get("shape_complementarity", 0),
                "mpnn_score": design.metrics.get("mpnn_score", 0),
            }

            rows.append(
                {
                    "design_id": design_id,
                    "sequence": design.sequence,
                    "structure_url": design.structure_path,
                    "metrics": metrics,
                    "design_run_id": design_run_id,
                }
            )

        result = self._table("design_run_sequences").insert(rows).execute()

        return [row["id"] for row in result.data]

    def get_approved_designs(
        self,
        design_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get designs that have been approved in ProteinRoom.

        Args:
            design_run_id: Optional filter by design run

        Returns:
            List of approved design records with sequences
        """
        # Query designs joined with reviews where has_passed = true
        query = (
            self._table("design_run_sequences")
            .select("*, result_reviews!inner(has_passed, reviewed_at, reviewer)")
            .eq("result_reviews.has_passed", True)
        )

        if design_run_id:
            query = query.eq("design_run_id", design_run_id)

        result = query.execute()
        return result.data

    def get_rejected_designs(
        self,
        design_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get designs that have been rejected in ProteinRoom.

        Useful for feeding back to active learning / Bayesian optimization.

        Args:
            design_run_id: Optional filter by design run

        Returns:
            List of rejected design records with rejection notes
        """
        query = self._table("failed_sequences").select("*")

        if design_run_id:
            query = query.eq("design_run_id", design_run_id)

        result = query.execute()
        return result.data

    def export_sequences_for_foundry(
        self,
        design_run_id: str | None = None,
    ) -> dict[str, str]:
        """Export approved sequences as dict for Lab.create_experiment().

        Args:
            design_run_id: Optional filter by design run

        Returns:
            Dict mapping sequence name to sequence string
        """
        approved = self.get_approved_designs(design_run_id)

        return {
            design["design_id"]: design["sequence"] for design in approved if design.get("sequence")
        }
