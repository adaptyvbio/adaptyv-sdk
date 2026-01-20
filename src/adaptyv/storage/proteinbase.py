"""Proteinbase client for publishing design collections.

This module provides a client for publishing approved designs to Proteinbase
(https://proteinbase.com) as collections.
"""

from __future__ import annotations

from typing import Any

import httpx


class ProteinbaseClient:
    """Client for publishing designs to Proteinbase.

    Proteinbase is a public protein database where users can share
    their designed proteins as collections.

    Usage:
        client = ProteinbaseClient()
        result = client.publish_collection(
            name="CD20 Binders",
            summary="Designed binders targeting CD20",
            proteins=[{"sequence": "MKTL...", "pdb_url": "..."}],
            design_method="design-a-protein",
            design_params={"num_samples": 10},
            auth_token="...",
        )
    """

    def __init__(self, base_url: str = "https://proteinbase.com"):
        """Initialize client.

        Args:
            base_url: Proteinbase API base URL
        """
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=30.0)

    def publish_collection(
        self,
        *,
        name: str,
        summary: str,
        proteins: list[dict[str, Any]],
        design_method: str,
        design_params: dict[str, Any],
        auth_token: str,
    ) -> dict[str, Any]:
        """Publish designs as a Proteinbase collection.

        Args:
            name: Collection name
            summary: Collection description/summary
            proteins: List of protein dicts with sequence, pdb_url, metrics
            design_method: Design method used (e.g., "design-a-protein", "bindcraft")
            design_params: Design parameters used
            auth_token: Proteinbase auth token (from Google OAuth)

        Returns:
            API response with collection_id

        Raises:
            httpx.HTTPStatusError: On API errors
        """
        response = self._client.post(
            f"{self.base_url}/api/collections/create",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={
                "name": name,
                "summary": summary,
                "proteins": proteins,
                "designMethod": design_method,
                "designParams": design_params,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_collection(self, collection_id: str) -> dict[str, Any]:
        """Get a collection by ID.

        Args:
            collection_id: Collection UUID

        Returns:
            Collection data
        """
        response = self._client.get(f"{self.base_url}/api/collections/{collection_id}")
        response.raise_for_status()
        return response.json()

    def add_proteins_to_collection(
        self,
        collection_id: str,
        proteins: list[dict[str, Any]],
        auth_token: str,
    ) -> dict[str, Any]:
        """Add proteins to an existing collection.

        Args:
            collection_id: Collection UUID
            proteins: List of protein dicts
            auth_token: Proteinbase auth token

        Returns:
            API response
        """
        response = self._client.post(
            f"{self.base_url}/api/collections/{collection_id}/proteins",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"proteins": proteins},
        )
        response.raise_for_status()
        return response.json()


__all__ = ["ProteinbaseClient"]
