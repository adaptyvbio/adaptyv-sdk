"""High-level Lab interface for Adaptyv SDK."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from functools import wraps
from typing import Any, TypeVar, cast

from adaptyv.client.foundry import FoundryClientProtocol, get_client
from adaptyv.config import AdaptyvConfig
from adaptyv.exceptions import AuthenticationError, NotFoundError, ValidationError
from adaptyv.types.generated import ExperimentSpec, ExperimentType, Method
from adaptyv.types.internal import ExperimentResult
from adaptyv.validation import (
    UUID_RE,
    normalize_sequences,
    validate_sequences,
    validate_url,
    validate_uuid,
)

F = TypeVar("F", bound=Callable[..., Any])


class Lab:
    """High-level interface for protein design experiments.

    Usage:
        lab = Lab.setup()  # Reads ADAPTYV_API_KEY from env

        @lab.experiment(target="PD-L1")
        def design_binders():
            return ["MVKVGVNG...", "MKVLVAG..."]

        result = design_binders()
        print(f"Experiment: {result.experiment_url}")

    Can also be used as a context manager:
        with Lab.setup() as lab:
            result = lab.create_experiment(...)
        # Client is automatically closed
    """

    def __init__(self, client: FoundryClientProtocol, config: AdaptyvConfig):
        """Initialize Lab with a configured client.

        Use Lab.setup() instead for automatic configuration.

        Args:
            client: Configured FoundryClient instance
            config: AdaptyvConfig with configuration
        """
        self._client = client
        self._config = config

    @classmethod
    def setup(
        cls,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        organization_id: str | None = None,
    ) -> Lab:
        """Set up Lab with API credentials.

        Configuration is loaded automatically from environment variables:
        - ADAPTYV_API_KEY: API key (required)
        - ADAPTYV_API_URL: Custom API URL
        - ADAPTYV_ORGANIZATION_ID: Default organization

        Args:
            api_key: Foundry API key. If not provided, reads from env.
            base_url: Optional custom API URL.
            organization_id: Organization UUID. If not provided, reads from env.

        Returns:
            Configured Lab instance.

        Raises:
            AuthenticationError: If ADAPTYV_API_KEY is not set and api_key not provided.
        """
        config = AdaptyvConfig()

        # Override with explicit args
        final_api_key = api_key or config.api_key
        final_base_url = base_url or config.api_url
        final_org_id = organization_id or config.organization_id

        if not final_api_key:
            raise AuthenticationError(
                "ADAPTYV_API_KEY not set. Set environment variable or pass api_key parameter."
            )

        if not final_base_url:
            raise ValidationError(
                "ADAPTYV_API_URL not set. Set environment variable or pass base_url parameter."
            )

        # Create config with final values
        final_config = AdaptyvConfig(
            api_key=final_api_key,
            api_url=final_base_url,
            organization_id=final_org_id,
            timeout=config.timeout,
            mock_mode=config.mock_mode,
        )

        client = get_client(
            api_key=final_api_key,
            base_url=final_base_url,
            settings=final_config,
        )

        return cls(client, final_config)

    def _build_spec(
        self,
        sequences: dict[str, str],
        *,
        target_id: str | None,
        experiment_type: str,
        method: str,
        n_replicates: int,
    ) -> ExperimentSpec:
        """Build ExperimentSpec from parameters."""
        return ExperimentSpec(
            experiment_type=ExperimentType(experiment_type),
            method=Method(method),
            target_id=target_id,
            sequences=sequences,
            n_replicates=n_replicates,
        )

    def experiment(
        self,
        *,
        target: str,
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
            auto_confirm: Automatically confirm quote (requires pre-approved budget)
            webhook_url: Webhook URL for status updates
            experiment_name: Custom experiment name
            experiment_type: Type of experiment (screening, affinity, thermostability)
            method: Measurement method (bli, spr)
            n_replicates: Number of technical replicates

        Returns:
            Decorator that wraps design function to create experiment.

        Example:
            @lab.experiment(target="PD-L1")
            def design_pdl1():
                return ["MVKVGVNG...", "MKVLVAG..."]

            result = design_pdl1()
        """

        def decorator(func: F) -> Callable[..., ExperimentResult]:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> ExperimentResult:
                # Execute design function to get sequences
                sequences = func(*args, **kwargs)

                if not sequences:
                    raise ValidationError("Design function returned no sequences")

                if not isinstance(sequences, list | tuple | dict):
                    raise ValidationError(
                        "Design function must return a list or dict of sequences, "
                        f"got {type(sequences)}"
                    )

                seq_dict = normalize_sequences(cast("list[str] | dict[str, str]", sequences))

                # Create experiment name
                name = experiment_name or f"{target}_{len(sequences)}designs"

                spec = self._build_spec(
                    seq_dict,
                    target_id=target if UUID_RE.match(target) else None,
                    experiment_type=experiment_type,
                    method=method,
                    n_replicates=n_replicates,
                )

                # Create experiment
                response = self._client.experiments.create(
                    name=name,
                    experiment_spec=spec,
                    organization_id=self._config.organization_id,
                    webhook_url=webhook_url,
                )

                # Get full experiment info
                exp_info = self._client.experiments.get(response.experiment_id)

                # Build result
                result = ExperimentResult(
                    experiment_id=response.experiment_id,
                    experiment_url=exp_info.experiment_url,
                    status=exp_info.status,
                    sequences_submitted=len(sequences),
                )

                # Auto-confirm if requested
                if auto_confirm:
                    submit_response = self._client.experiments.submit(response.experiment_id)
                    result.confirmed_at = submit_response.confirmed_at
                    result.status = submit_response.status

                return result

            return wrapper

        return decorator

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
        """Create an experiment directly (without decorator).

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
        # Validate inputs
        validate_sequences(sequences)
        if webhook_url:
            validate_url(webhook_url, "webhook_url")
        if target_id:
            validate_uuid(target_id, "target_id")

        seq_dict = normalize_sequences(sequences)
        spec = self._build_spec(
            seq_dict,
            target_id=target_id,
            experiment_type=experiment_type,
            method=method,
            n_replicates=n_replicates,
        )

        response = self._client.experiments.create(
            name=name,
            experiment_spec=spec,
            organization_id=self._config.organization_id,
            webhook_url=webhook_url,
        )

        exp_info = self._client.experiments.get(response.experiment_id)

        return ExperimentResult(
            experiment_id=response.experiment_id,
            experiment_url=exp_info.experiment_url,
            status=exp_info.status,
            sequences_submitted=len(seq_dict),
        )

    def get_experiment(self, experiment_id: str) -> ExperimentResult:
        """Get experiment status and results.

        Args:
            experiment_id: Experiment UUID

        Returns:
            ExperimentResult with current status
        """
        validate_uuid(experiment_id, "experiment_id")
        exp_info = self._client.experiments.get(experiment_id)

        return ExperimentResult(
            experiment_id=exp_info.id,
            experiment_url=exp_info.experiment_url,
            status=exp_info.status,
            results_status=exp_info.results_status,
        )

    def confirm_experiment(
        self,
        experiment_id: str,
        *,
        poll: bool = True,
        poll_interval: float = 1.0,
        timeout: float = 30.0,
    ) -> ExperimentResult:
        """Confirm experiment quote to start production.

        Waits for the Stripe quote to be ready before confirming. Quote generation
        is async - the API may return before the quote is available.

        Args:
            experiment_id: Experiment UUID
            poll: If True, poll for quote readiness before confirming (default True)
            poll_interval: Seconds between poll attempts (default 1.0)
            timeout: Maximum seconds to wait for quote (default 30.0)

        Returns:
            ExperimentResult with updated status

        Raises:
            TimeoutError: If quote not ready within timeout
            APIError: If confirmation fails (e.g., 409 if not ready)
        """
        validate_uuid(experiment_id, "experiment_id")

        if poll:
            self._wait_for_quote(experiment_id, poll_interval, timeout)

        submit_response = self._client.experiments.submit(experiment_id)
        exp_info = self._client.experiments.get(experiment_id)

        return ExperimentResult(
            experiment_id=exp_info.id,
            experiment_url=exp_info.experiment_url,
            status=exp_info.status,
            confirmed_at=submit_response.confirmed_at,
        )

    def _wait_for_quote(
        self,
        experiment_id: str,
        poll_interval: float,
        timeout: float,
    ) -> None:
        """Poll until experiment has a quote ready.

        Args:
            experiment_id: Experiment UUID
            poll_interval: Seconds between attempts
            timeout: Maximum wait time

        Raises:
            TimeoutError: If quote not ready within timeout
        """
        start = time.monotonic()
        deadline = start + timeout

        while time.monotonic() < deadline:
            try:
                quote = self._client.experiments.get_quote(experiment_id)
                if quote.stripe_quote_url:
                    return
            except NotFoundError:
                pass  # Quote not yet available

            time.sleep(poll_interval)

        raise TimeoutError(
            f"Quote not ready after {timeout}s for experiment {experiment_id}. "
            "The Stripe quote may still be generating. Try again in a few seconds."
        )

    def list_targets(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List available targets from catalog.

        For single page of results. Use list_all_targets() to iterate through all.

        Args:
            limit: Maximum number of targets to return (max 50)
            offset: Number of targets to skip

        Returns:
            List of target dicts
        """
        result = self._client.targets.list(limit=limit, offset=offset)
        return [t.model_dump(mode="json", exclude_none=True) for t in result.items]

    def list_all_targets(self, *, limit: int = 50) -> Iterator[dict[str, Any]]:
        """Iterate through all targets from catalog with automatic pagination.

        This method handles pagination automatically, yielding one target at a time.
        Rate limits are handled by the underlying client's retry logic.

        Args:
            limit: Items per page (max 50)

        Yields:
            Target dicts one at a time

        Example:
            for target in lab.list_all_targets():
                print(target["name"])
        """
        offset = 0
        while True:
            result = self._client.targets.list(limit=limit, offset=offset)
            for target in result.items:
                yield target.model_dump(mode="json", exclude_none=True)

            # Check if we've fetched all targets
            if len(result.items) < limit:
                break
            offset += limit

    def search_targets(self, query: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """Search targets by name.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching target dicts
        """
        result = self._client.targets.search(query, limit=limit)
        return [t.model_dump(mode="json", exclude_none=True) for t in result.items]

    @property
    def client(self) -> FoundryClientProtocol:
        """Access underlying Foundry client for advanced usage."""
        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client.

        Call this when you're done using the Lab instance to release resources.
        Alternatively, use Lab as a context manager:

            with Lab.setup() as lab:
                result = lab.create_experiment(...)
            # Client is automatically closed
        """
        self._client.close()

    def __enter__(self) -> Lab:
        """Enter context manager."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager and close client."""
        self.close()
