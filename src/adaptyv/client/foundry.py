"""Foundry API client for Adaptyv Lab SDK."""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

import httpx

from adaptyv.config import (
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    RetryConfig,
)

if TYPE_CHECKING:
    from adaptyv.config import AdaptyvConfig

from adaptyv.exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ValidationError,
)
from adaptyv.types.generated import (
    CreateExpRequest,
    CreateExpResponse,
    ExperimentConfirmationResponse,
    ExperimentInvoiceResponse,
    ExperimentQuoteResponse,
    ExperimentSpec,
    ExperimentType,
    ExpInfo,
    ExpList,
    ResultInfoModel,
    ResultList,
    SequenceAddResponse,
    SequenceEntry,
    SequenceInfoModel,
    SequenceList,
    TargetInfo,
    TargetList,
    UpdateList,
)

logger = logging.getLogger("adaptyv")


@runtime_checkable
class ExperimentsAPIProtocol(Protocol):
    """Protocol for experiments API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        status: str | None = None,
        state: str | None = None,
        project_id: str | None = None,
    ) -> ExpList: ...
    def create(
        self,
        name: str,
        experiment_spec: ExperimentSpec | dict[str, Any],
        *,
        organization_id: str | None = None,
        webhook_url: str | None = None,
        experiment_id: str | None = None,
        confirmed: bool = False,
        auto_link_material: bool = False,
    ) -> CreateExpResponse: ...
    def get(self, experiment_id: str) -> ExpInfo: ...
    def confirm(self, experiment_id: str) -> ExperimentConfirmationResponse: ...
    def get_quote(self, experiment_id: str) -> ExperimentQuoteResponse: ...
    def get_invoice(self, experiment_id: str) -> ExperimentInvoiceResponse: ...
    def list_updates(
        self,
        experiment_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        update_type: str | None = None,
    ) -> UpdateList: ...
    def get_results(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ResultList: ...
    def update_priority(self, experiment_id: str, priority: int) -> dict[str, Any]: ...


@runtime_checkable
class TargetsAPIProtocol(Protocol):
    """Protocol for targets API."""

    def get(self, target_id: str) -> TargetInfo: ...
    def list(
        self, *, limit: int = 50, offset: int = 0, selfservice_only: bool = False
    ) -> TargetList: ...
    def search(
        self, query: str, *, limit: int = 50, selfservice_only: bool = False
    ) -> TargetList: ...


@runtime_checkable
class UpdatesAPIProtocol(Protocol):
    """Protocol for global updates API."""

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
        experiment_id: str | None = None,
        experiment_ids: str | None = None,
        update_type: str | None = None,
    ) -> UpdateList: ...


@runtime_checkable
class SequencesAPIProtocol(Protocol):
    """Protocol for sequences API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        experiment_id: str | None = None,
        search: str | None = None,
    ) -> SequenceList: ...
    def create(
        self,
        experiment_code: str,
        sequences: list[SequenceEntry] | list[dict[str, Any]],
    ) -> SequenceAddResponse: ...
    def get(self, sequence_id: str) -> SequenceInfoModel: ...


@runtime_checkable
class ResultsAPIProtocol(Protocol):
    """Protocol for results API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        experiment_id: str | None = None,
    ) -> ResultList: ...
    def get(self, result_id: str) -> ResultInfoModel: ...


@runtime_checkable
class FoundryClientProtocol(Protocol):
    """Protocol that all Foundry clients must implement."""

    experiments: ExperimentsAPIProtocol
    targets: TargetsAPIProtocol
    updates: UpdatesAPIProtocol
    sequences: SequencesAPIProtocol
    results: ResultsAPIProtocol

    def close(self) -> None: ...


_client_cache: dict[str, Any] = {}


def get_client(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    timeout: int | None = None,
    retries: int = DEFAULT_RETRIES,
    settings: AdaptyvConfig | None = None,
) -> FoundryClientProtocol:
    """Get or create a cached FoundryClient.

    This avoids creating new HTTP connections for every request.
    Clients are cached by API key.

    Args:
        api_key: Foundry API key. If None, reads from settings/env.
        base_url: Override API base URL.
        timeout: Request timeout in seconds.
        retries: Number of retries for connection failures.
        settings: AdaptyvConfig instance (optional, auto-created if None).

    Returns:
        Cached FoundryClient.
    """
    from adaptyv.config import AdaptyvConfig

    # Load settings if not provided
    if settings is None:
        settings = AdaptyvConfig()

    # Resolve values from settings or explicit args
    resolved_key = api_key or settings.api_key
    resolved_url = base_url or settings.api_url
    resolved_timeout = timeout if timeout is not None else settings.timeout

    if not resolved_url:
        raise ValueError(
            "API URL is required. Either set ADAPTYV_API_URL environment variable "
            "or pass base_url parameter."
        )

    cache_key = resolved_key or "default"

    if cache_key not in _client_cache:
        _client_cache[cache_key] = FoundryClient(
            resolved_key,
            base_url=resolved_url,
            timeout=resolved_timeout,
            retries=retries,
        )

    return cast(FoundryClientProtocol, _client_cache[cache_key])


class ExperimentsAPI:
    """Experiments endpoint methods."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        status: str | None = None,
        state: str | None = None,
        project_id: str | None = None,
    ) -> ExpList:
        """List experiments with optional filters.

        Args:
            limit: Maximum number of experiments to return.
            offset: Number of experiments to skip.
            search: Case-insensitive search term.
            status: Filter by status (comma-separated for multiple).
            state: Filter by state.
            project_id: Filter by project ID.

        Returns:
            List of experiments matching filters.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search
        if status:
            params["status"] = status
        if state:
            params["state"] = state
        if project_id:
            params["project_id"] = project_id
        response = self._client._get("/experiments", params=params)
        return ExpList(**response)

    def create(
        self,
        name: str,
        experiment_spec: ExperimentSpec | dict[str, Any],
        *,
        organization_id: str | None = None,
        webhook_url: str | None = None,
        experiment_id: str | None = None,
        confirmed: bool = False,
        auto_link_material: bool = False,
    ) -> CreateExpResponse:
        """Create a new experiment.

        Args:
            name: Human-readable experiment name.
            experiment_spec: Experiment specification (type, target, sequences).
            organization_id: Organization ID (for multi-org accounts).
            webhook_url: URL for status update callbacks.
            experiment_id: UUID for idempotent updates.
            confirmed: If True, skip draft and submit directly.
            auto_link_material: If True, auto-link inventory material.

        Returns:
            Response with experiment_id.
        """
        if isinstance(experiment_spec, dict):
            experiment_spec = ExperimentSpec(**experiment_spec)

        # Client-side validation for experiment-type requirements
        exp_type = experiment_spec.experiment_type

        # Validate sequences are provided
        if not experiment_spec.sequences:
            raise ValidationError("Experiment requires at least one sequence")

        # Affinity and screening require target_id
        if exp_type in (ExperimentType.affinity, ExperimentType.screening):
            if not experiment_spec.target_id:
                raise ValidationError(
                    f"{exp_type.value} experiments require target_id"
                )

        # Affinity requires antigen_concentrations
        if exp_type == ExperimentType.affinity:
            if not experiment_spec.antigen_concentrations:
                raise ValidationError(
                    "Affinity experiments require antigen_concentrations"
                )

        # n_replicates must be >= 1 if provided
        if experiment_spec.n_replicates is not None and experiment_spec.n_replicates < 1:
            raise ValidationError("n_replicates must be >= 1")

        request = CreateExpRequest(
            name=name,
            experiment_spec=experiment_spec,
            webhook_url=webhook_url,
            id=experiment_id,
        )

        payload = request.model_dump(exclude_none=True)
        if organization_id:
            payload["organization_id"] = organization_id
        if confirmed:
            payload["skip_draft"] = True
        if auto_link_material:
            payload["auto_link_material"] = True

        response = self._client._post("/experiments", payload)
        return CreateExpResponse(**response)

    def get(self, experiment_id: str) -> ExpInfo:
        """Get experiment by ID."""
        response = self._client._get(f"/experiments/{experiment_id}")
        return ExpInfo(**response)

    def confirm(self, experiment_id: str) -> ExperimentConfirmationResponse:
        """Confirm experiment quote to start production."""
        response = self._client._post(f"/experiments/{experiment_id}/confirm", {})
        return ExperimentConfirmationResponse(**response)

    def get_quote(self, experiment_id: str) -> ExperimentQuoteResponse:
        """Get experiment quote details."""
        response = self._client._get(f"/experiments/{experiment_id}/quote")
        return ExperimentQuoteResponse(**response)

    def get_invoice(self, experiment_id: str) -> ExperimentInvoiceResponse:
        """Get experiment invoice details."""
        response = self._client._get(f"/experiments/{experiment_id}/invoice")
        return ExperimentInvoiceResponse(**response)

    def list_updates(
        self,
        experiment_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        update_type: str | None = None,
    ) -> UpdateList:
        """List experiment status updates."""
        params: dict[str, Any] = {
            k: v
            for k, v in {"limit": limit, "cursor": cursor, "type": update_type}.items()
            if v is not None
        }
        response = self._client._get(f"/experiments/{experiment_id}/updates", params=params)
        return UpdateList(**response)

    def cost_estimate(
        self,
        experiment_spec: ExperimentSpec | dict[str, Any],
    ) -> dict[str, Any]:
        """Estimate experiment cost without creating it.

        Note: Returns raw dict since API response structure varies.
        """
        if isinstance(experiment_spec, dict):
            experiment_spec = ExperimentSpec(**experiment_spec)

        payload = {"experiment_spec": experiment_spec.model_dump(exclude_none=True)}
        return self._client._post("/experiments/costestimate", payload)

    def get_results(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ResultList:
        """Get results for a specific experiment.

        Args:
            experiment_id: Experiment UUID.
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            Paginated list of results for the experiment.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        response = self._client._get(f"/experiments/{experiment_id}/results", params=params)
        return ResultList(**response)

    def update_priority(self, experiment_id: str, priority: int) -> dict[str, Any]:
        """Update experiment priority.

        Args:
            experiment_id: Experiment UUID.
            priority: New priority value.

        Returns:
            Response from the API.
        """
        return self._client._post(
            f"/experiments/{experiment_id}/update-priority",
            {"priority": priority},
        )


class TargetsAPI:
    """Targets endpoint methods."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def get(self, target_id: str) -> TargetInfo:
        """Get target by ID."""
        response = self._client._get(f"/targets/{target_id}")
        return TargetInfo(**response)

    def list(
        self, *, limit: int = 50, offset: int = 0, selfservice_only: bool = False
    ) -> TargetList:
        """List available targets.

        Args:
            limit: Maximum number of targets to return.
            offset: Number of targets to skip.
            selfservice_only: If True, only return self-service targets.

        Returns:
            Paginated list of targets.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if selfservice_only:
            params["selfservice_only"] = "true"
        response = self._client._get("/targets", params=params)
        return TargetList(**response)

    def search(
        self, query: str, *, limit: int = 50, selfservice_only: bool = False
    ) -> TargetList:
        """Search targets by name/description.

        Args:
            query: Search term.
            limit: Maximum number of targets to return.
            selfservice_only: If True, only return self-service targets.

        Returns:
            List of matching targets.
        """
        params: dict[str, Any] = {"search": query, "limit": limit}
        if selfservice_only:
            params["selfservice_only"] = "true"
        response = self._client._get("/targets", params=params)
        return TargetList(**response)


class UpdatesAPI:
    """Global updates endpoint for cross-experiment update feed."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
        experiment_id: str | None = None,
        experiment_ids: str | None = None,
        update_type: str | None = None,
    ) -> UpdateList:
        """List updates across all experiments.

        Args:
            cursor: Pagination cursor (use last update ID).
            limit: Maximum number of updates to return.
            experiment_id: Filter to single experiment.
            experiment_ids: Filter to multiple experiments (comma-separated).
            update_type: Filter by update type.

        Returns:
            List of updates with next_cursor for pagination.
        """
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if experiment_id:
            params["experiment_id"] = experiment_id
        if experiment_ids:
            params["experiment_ids"] = experiment_ids
        if update_type:
            params["type"] = update_type
        response = self._client._get("/updates", params=params)
        return UpdateList(**response)


class SequencesAPI:
    """Sequences endpoint for managing experiment sequences."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        experiment_id: str | None = None,
        search: str | None = None,
    ) -> SequenceList:
        """List sequences from accessible experiments.

        Args:
            limit: Maximum number of sequences to return.
            offset: Number of sequences to skip.
            experiment_id: Filter by experiment UUID.
            search: Search in name or FASTA content.

        Returns:
            Paginated list of sequences.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if experiment_id:
            params["experiment_id"] = experiment_id
        if search:
            params["search"] = search
        response = self._client._get("/sequences", params=params)
        return SequenceList(**response)

    def create(
        self,
        experiment_code: str,
        sequences: list[SequenceEntry] | list[dict[str, Any]],
    ) -> SequenceAddResponse:
        """Append sequences to a draft experiment.

        Args:
            experiment_code: Human-readable experiment code (e.g., "PROJ-001").
            sequences: List of sequences to add.

        Returns:
            Response with added count and sequence IDs.
        """
        seq_entries = [
            s if isinstance(s, SequenceEntry) else SequenceEntry(**s) for s in sequences
        ]
        payload = {
            "experiment_code": experiment_code,
            "sequences": [s.model_dump(exclude_none=True) for s in seq_entries],
        }
        response = self._client._post("/sequences", payload)
        return SequenceAddResponse(**response)

    def get(self, sequence_id: str) -> SequenceInfoModel:
        """Get full details for a specific sequence.

        Args:
            sequence_id: Sequence UUID.

        Returns:
            Full sequence details including metadata.
        """
        response = self._client._get(f"/sequences/{sequence_id}")
        return SequenceInfoModel(**response)


class ResultsAPI:
    """Results endpoint for accessing experiment results."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        experiment_id: str | None = None,
    ) -> ResultList:
        """List completed analysis results.

        Args:
            limit: Maximum number of results to return.
            offset: Number of results to skip.
            experiment_id: Filter by experiment UUID.

        Returns:
            Paginated list of results.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if experiment_id:
            params["experiment_id"] = experiment_id
        response = self._client._get("/results", params=params)
        return ResultList(**response)

    def get(self, result_id: str) -> ResultInfoModel:
        """Get full details for a specific result.

        Args:
            result_id: Result UUID.

        Returns:
            Full result details including kinetic parameters and data package URL.
        """
        response = self._client._get(f"/results/{result_id}")
        return ResultInfoModel(**response)


class FoundryClient:
    """Client for Adaptyv Foundry API.

    Features:
    - Exponential backoff retry for 429 and 5xx errors
    - Request correlation IDs for debugging
    - Structured error handling with request context
    - Cost estimation before experiment creation

    Usage:
        client = FoundryClient(api_key="...")

        # Create experiment
        exp = client.experiments.create(
            name="PD-L1 Binders",
            experiment_spec={
                "experiment_type": "screening",
                "target_id": "...",
                "sequences": {"design_1": "MVKVG..."},
            },
        )

        # Confirm quote
        client.experiments.confirm(exp.experiment_id)

        # Check status
        info = client.experiments.get(exp.experiment_id)

        # Estimate cost before creating
        estimate = client.experiments.cost_estimate({...})
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize Foundry client.

        Args:
            api_key: Foundry API key
            base_url: API base URL (required, set via ADAPTYV_API_URL env var)
            timeout: Request timeout in seconds
            retries: Number of retries for connection failures (transport-level)
            retry_config: Configuration for application-level retry with backoff
        """
        if not api_key:
            raise AuthenticationError("API key is required")

        self._base_url = base_url.rstrip("/")
        self._retry_config = retry_config or RetryConfig()
        transport = httpx.HTTPTransport(retries=retries)
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

        self.experiments = ExperimentsAPI(self)
        self.targets = TargetsAPI(self)
        self.updates = UpdatesAPI(self)
        self.sequences = SequencesAPI(self)
        self.results = ResultsAPI(self)

    def _generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for request tracking."""
        return f"sdk-{uuid.uuid4().hex[:12]}"

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make GET request with retry logic."""
        return self._request_with_retry("GET", path, params=params)

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make POST request with retry logic."""
        return self._request_with_retry("POST", path, json_data=data)

    def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute request with exponential backoff retry.

        Retries on:
        - 429 Rate Limit (respects Retry-After header)
        - 5xx Server Errors

        Does NOT retry on:
        - 4xx Client Errors (except 429)
        - Connection errors (handled by transport-level retries)
        """
        correlation_id = self._generate_correlation_id()
        last_error: APIError | None = None

        for attempt in range(self._retry_config.max_attempts + 1):
            try:
                start_time = time.monotonic()

                # Add correlation ID to headers
                headers = {"X-Correlation-ID": correlation_id}

                if method == "GET":
                    response = self._client.get(path, params=params, headers=headers)
                else:
                    response = self._client.post(path, json=json_data, headers=headers)

                elapsed_ms = (time.monotonic() - start_time) * 1000

                # Log request with timing
                logger.debug(
                    "%s %s completed in %.0fms (status=%d, correlation_id=%s)",
                    method,
                    path,
                    elapsed_ms,
                    response.status_code,
                    correlation_id,
                )

                return self._handle_response(response, path, correlation_id)

            except (RateLimitError, APIError) as e:
                last_error = e

                # Only retry if error is retryable and we have attempts left
                if not e.retryable or attempt >= self._retry_config.max_attempts:
                    raise

                # Calculate backoff time
                if isinstance(e, RateLimitError) and e.retry_after:
                    # Use server-provided retry-after if available
                    backoff = min(e.retry_after, self._retry_config.max_backoff)
                else:
                    backoff = self._retry_config.get_backoff(attempt)

                logger.warning(
                    "Retrying %s %s after %.1fs (attempt %d/%d, error: %s)",
                    method,
                    path,
                    backoff,
                    attempt + 1,
                    self._retry_config.max_attempts,
                    str(e),
                )

                time.sleep(backoff)

        # Should not reach here, but raise last error if we do
        if last_error:
            raise last_error
        raise RuntimeError("Unexpected retry loop exit")

    def _handle_response(
        self,
        response: httpx.Response,
        path: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Handle API response, raising appropriate exceptions with context."""
        # Extract request ID from response headers
        request_id = response.headers.get("X-Request-ID") or correlation_id

        if response.status_code < 400:
            return cast(dict[str, Any], response.json())

        # Try to parse error body
        try:
            body = response.json()
        except (ValueError, httpx.DecodingError):
            body = {"error": response.text}

        # Map status codes to exceptions with full context
        if response.status_code == 401:
            raise AuthenticationError("Invalid API key")

        if response.status_code == 403:
            raise PermissionDeniedError(
                body.get("error") or body.get("message") or "Permission denied",
                response_body=body,
                request_id=request_id,
                request_path=path,
            )

        if response.status_code == 404:
            raise NotFoundError(
                "Resource",
                "unknown",
                request_id=request_id,
                request_path=path,
            )

        if response.status_code == 429:
            # Parse Retry-After header
            retry_after: float | None = None
            retry_header = response.headers.get("Retry-After")
            if retry_header:
                try:
                    retry_after = float(retry_header)
                except ValueError:
                    pass
            raise RateLimitError(
                "Rate limit exceeded",
                retry_after=retry_after,
                request_id=request_id,
                request_path=path,
            )

        if response.status_code == 422:
            raise ValidationError(f"Validation error: {body.get('detail', body)}")

        if response.status_code == 400:
            # API may return {"experiment_id": ""} with error message discarded (foundry-api-public#14)
            error_msg = body.get("error") or body.get("message") or body.get("detail")
            if not error_msg and body == {"experiment_id": ""}:
                error_msg = (
                    "Request rejected. API discards error details (foundry-api-public#14). "
                    "Common causes: (1) API key lacks create_experiment permission, "
                    "(2) missing target_id, (3) empty sequences, (4) invalid UUIDs. "
                    "Contact support@adaptyvbio.com to verify API key permissions."
                )
            raise ValidationError(f"Bad request: {error_msg or body}")

        raise APIError(
            response.status_code,
            response.text,
            body,
            request_id=request_id,
            request_path=path,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> FoundryClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
