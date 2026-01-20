"""Zero-config singleton Lab instance.

Usage:
    from adaptyv import lab

    @lab.experiment(target="PD-L1", workflow="bindcraft")
    def design_binders():
        return ["MVKVGVNG...", "MKVLVAG..."]

    result = design_binders()

The singleton auto-reads ADAPTYV_API_KEY from environment on first use.
If the key is missing, raises a clear error with setup instructions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from adaptyv.lab import Lab
    from adaptyv.types.internal import ExperimentResult

F = TypeVar("F", bound=Callable[..., Any])


class DefaultLab:
    """Lazy-initialized singleton Lab instance.

    This class wraps the Lab class and initializes it on first use.
    All Lab methods are exposed as properties/methods that delegate
    to the underlying Lab instance.

    The singleton reads ADAPTYV_API_KEY from environment on first use.
    """

    def __init__(self) -> None:
        self._lab: Lab | None = None

    def _get_lab(self) -> Lab:
        """Get or create the underlying Lab instance."""
        if self._lab is None:
            from adaptyv.lab import Lab

            self._lab = Lab.setup()
        return self._lab

    def configure(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        organization_id: str | None = None,
    ) -> None:
        """Reconfigure the singleton with custom settings.

        Call this before first use if you need to override environment variables.

        Args:
            api_key: Foundry API key (overrides ADAPTYV_API_KEY)
            base_url: Custom API URL (overrides ADAPTYV_API_URL)
            organization_id: Default organization (overrides ADAPTYV_ORGANIZATION_ID)
        """
        from adaptyv.lab import Lab

        self._lab = Lab.setup(
            api_key=api_key,
            base_url=base_url,
            organization_id=organization_id,
        )

    def experiment(
        self,
        *,
        target: str,
        workflow: str = "bindcraft",
        auto_confirm: bool = False,
        webhook_url: str | None = None,
        experiment_name: str | None = None,
        experiment_type: str = "screening",
        method: str = "bli",
        n_replicates: int = 3,
    ) -> Callable[[F], Callable[..., ExperimentResult]]:
        """Decorator for design experiment functions.

        Args:
            target: Target name or ID for binding experiments
            workflow: Design workflow ("bindcraft" or "germinal")
            auto_confirm: Automatically confirm quote
            webhook_url: Webhook URL for status updates
            experiment_name: Custom experiment name
            experiment_type: Type of experiment (screening, affinity, thermostability)
            method: Measurement method (bli, spr)
            n_replicates: Number of technical replicates

        Returns:
            Decorator that wraps design function to create experiment.

        Example:
            from adaptyv import lab

            @lab.experiment(target="PD-L1", workflow="bindcraft")
            def design_pdl1():
                return ["MVKVGVNG...", "MKVLVAG..."]

            result = design_pdl1()
        """
        return self._get_lab().experiment(
            target=target,
            workflow=workflow,
            auto_confirm=auto_confirm,
            webhook_url=webhook_url,
            experiment_name=experiment_name,
            experiment_type=experiment_type,
            method=method,
            n_replicates=n_replicates,
        )

    def create_experiment(
        self,
        name: str,
        sequences: list[str] | dict[str, str],
        *,
        target_id: str | None = None,
        experiment_type: str = "screening",
        method: str = "bli",
        n_replicates: int = 3,
        webhook_url: str | None = None,
    ) -> ExperimentResult:
        """Create an experiment directly.

        Args:
            name: Experiment name
            sequences: List of sequences or dict mapping names to sequences
            target_id: Target UUID from catalog
            experiment_type: Type of experiment
            method: Measurement method
            n_replicates: Technical replicates
            webhook_url: Status update webhook

        Returns:
            ExperimentResult with experiment details
        """
        return self._get_lab().create_experiment(
            name=name,
            sequences=sequences,
            target_id=target_id,
            experiment_type=experiment_type,
            method=method,
            n_replicates=n_replicates,
            webhook_url=webhook_url,
        )

    def get_experiment(self, experiment_id: str) -> ExperimentResult:
        """Get experiment status and results.

        Args:
            experiment_id: Experiment UUID

        Returns:
            ExperimentResult with current status
        """
        return self._get_lab().get_experiment(experiment_id)

    def confirm_experiment(
        self,
        experiment_id: str,
        *,
        poll: bool = True,
        poll_interval: float = 1.0,
        timeout: float = 30.0,
    ) -> ExperimentResult:
        """Confirm experiment quote to start production.

        Args:
            experiment_id: Experiment UUID
            poll: If True, poll for quote readiness before confirming
            poll_interval: Seconds between poll attempts
            timeout: Maximum seconds to wait for quote

        Returns:
            ExperimentResult with updated status
        """
        return self._get_lab().confirm_experiment(
            experiment_id,
            poll=poll,
            poll_interval=poll_interval,
            timeout=timeout,
        )

    def list_targets(self, *, page: int = 1, per_page: int = 50) -> list[dict[str, Any]]:
        """List available targets from catalog.

        For single page of results. Use list_all_targets() to iterate through all.

        Args:
            page: Page number (1-indexed)
            per_page: Items per page (max 50)

        Returns:
            List of target dicts
        """
        return self._get_lab().list_targets(page=page, per_page=per_page)

    def list_all_targets(self, *, per_page: int = 50) -> Iterator[dict[str, Any]]:
        """Iterate through all targets from catalog with automatic pagination.

        This method handles pagination automatically, yielding one target at a time.
        Rate limits are handled by the underlying client's retry logic.

        Args:
            per_page: Items per page (max 50)

        Yields:
            Target dicts one at a time

        Example:
            from adaptyv import lab

            for target in lab.list_all_targets():
                print(target["name"])
        """
        return self._get_lab().list_all_targets(per_page=per_page)

    def search_targets(self, query: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Search targets by name.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching target dicts
        """
        return self._get_lab().search_targets(query, limit=limit)

    @property
    def client(self) -> Any:
        """Access underlying Foundry client for advanced usage."""
        return self._get_lab().client


# Module-level singleton instance
lab = DefaultLab()
