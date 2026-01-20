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
    FOUNDRY_API_BASE_URL,
    FOUNDRY_API_INTERNAL_URL,
    RetryConfig,
)

if TYPE_CHECKING:
    from adaptyv.config import FoundrySettings
from adaptyv.exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
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
    ExperimentStatus,
    ExperimentType,
    ExpInfo,
    ExpList,
    ResultsStatus,
    TargetInfo,
    TargetList,
    TargetListItem,
    UpdateList,
)

logger = logging.getLogger("adaptyv")


# =============================================================================
# Protocol Definitions
# =============================================================================


@runtime_checkable
class ExperimentsAPIProtocol(Protocol):
    """Protocol for experiments API."""

    def list(self) -> ExpList: ...
    def create(
        self,
        name: str,
        experiment_spec: ExperimentSpec | dict[str, Any],
        *,
        organization_id: str | None = None,
        webhook_url: str | None = None,
        experiment_id: str | None = None,
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


@runtime_checkable
class TargetsAPIProtocol(Protocol):
    """Protocol for targets API."""

    def get(self, target_id: str) -> TargetInfo: ...
    def list(self, *, page: int = 1, per_page: int = 50) -> TargetList: ...
    def search(self, query: str, *, limit: int = 50) -> TargetList: ...


@runtime_checkable
class FoundryClientProtocol(Protocol):
    """Protocol that all Foundry clients must implement."""

    experiments: ExperimentsAPIProtocol
    targets: TargetsAPIProtocol

    def close(self) -> None: ...


# =============================================================================
# Client Cache
# =============================================================================

# Cached clients by API key (avoids creating new HTTP connections per request)
# Type is Any because Protocol structural typing doesn't work well with mypy
_client_cache: dict[str, Any] = {}


def get_client(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    timeout: int | None = None,
    retries: int = DEFAULT_RETRIES,
    settings: FoundrySettings | None = None,
) -> FoundryClientProtocol:
    """Get or create a cached FoundryClient.

    Returns PublicFoundryClient or InternalFoundryClient based on
    settings.api_type or ADAPTYV_API_TYPE env var.

    This avoids creating new HTTP connections for every request.
    Clients are cached by API key + api_type.

    When ADAPTYV_MOCK_MODE=1 is set, returns a MockFoundryClient that
    doesn't require an API key and returns predictable mock responses.

    Args:
        api_key: Foundry API key. If None, reads from settings/env.
        base_url: Override API base URL.
        timeout: Request timeout in seconds.
        retries: Number of retries for connection failures.
        settings: FoundrySettings instance (optional, auto-created if None).

    Returns:
        Cached FoundryClient, InternalFoundryClient, or MockFoundryClient.
    """
    from adaptyv.config import MOCK_MODE, FoundrySettings

    # Return mock client if mock mode is enabled
    if MOCK_MODE:
        cache_key = "mock"
        if cache_key not in _client_cache:
            _client_cache[cache_key] = MockFoundryClient()
        return cast(FoundryClientProtocol, _client_cache[cache_key])

    # Load settings if not provided
    if settings is None:
        settings = FoundrySettings()

    # Resolve values from settings or explicit args
    resolved_key = api_key or settings.api_key
    resolved_url = base_url or settings.get_base_url()
    resolved_timeout = timeout if timeout is not None else settings.timeout
    api_type = settings.api_type

    # Cache key includes api_type to separate public vs internal clients
    cache_key = f"{resolved_key}:{api_type}"

    if cache_key not in _client_cache:
        # Select client class based on api_type
        if api_type == "internal":
            _client_cache[cache_key] = InternalFoundryClient(
                resolved_key,
                base_url=resolved_url,
                timeout=resolved_timeout,
                retries=retries,
            )
        else:
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

    def list(self) -> ExpList:
        """List all experiments accessible to the authenticated user.

        Returns:
            ExpList with experiment summaries
        """
        response = self._client._get("/experiments")
        return ExpList(**response)

    def create(
        self,
        name: str,
        experiment_spec: ExperimentSpec | dict[str, Any],
        *,
        organization_id: str | None = None,
        webhook_url: str | None = None,
        experiment_id: str | None = None,
    ) -> CreateExpResponse:
        """Create a new experiment.

        Args:
            name: Human-readable experiment name
            experiment_spec: Experiment specification
            organization_id: Organization UUID (required if not in API key)
            webhook_url: Optional webhook for status updates
            experiment_id: Optional UUID for updates

        Returns:
            CreateExpResponse with experiment_id
        """
        if isinstance(experiment_spec, dict):
            experiment_spec = ExperimentSpec(**experiment_spec)

        request = CreateExpRequest(
            name=name,
            experiment_spec=experiment_spec,
            webhook_url=webhook_url,
            id=experiment_id,
        )

        response = self._client._post("/experiments", request.model_dump(exclude_none=True))
        return CreateExpResponse(**response)

    def get(self, experiment_id: str) -> ExpInfo:
        """Get experiment details by ID.

        Args:
            experiment_id: Experiment UUID

        Returns:
            ExpInfo with full experiment details
        """
        response = self._client._get(f"/experiments/{experiment_id}")
        return ExpInfo(**response)

    def confirm(self, experiment_id: str) -> ExperimentConfirmationResponse:
        """Confirm experiment quote to start production.

        Args:
            experiment_id: Experiment UUID

        Returns:
            ExperimentConfirmationResponse with confirmation details
        """
        response = self._client._post(f"/experiments/{experiment_id}/confirm", {})
        return ExperimentConfirmationResponse(**response)

    def get_quote(self, experiment_id: str) -> ExperimentQuoteResponse:
        """Get experiment quote details.

        Returns quote metadata including totals, currency, status, and expiration.
        Available once stripe_quote_id appears in experiment details.

        Args:
            experiment_id: Experiment UUID

        Returns:
            ExperimentQuoteResponse with quote details
        """
        response = self._client._get(f"/experiments/{experiment_id}/quote")
        return ExperimentQuoteResponse(**response)

    def get_invoice(self, experiment_id: str) -> ExperimentInvoiceResponse:
        """Get experiment invoice details.

        Returns invoice ID, hosted URL, and payment status.
        Available after experiment is confirmed.

        Args:
            experiment_id: Experiment UUID

        Returns:
            ExperimentInvoiceResponse with invoice details
        """
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
        """List experiment status updates.

        Returns updates in chronological order (oldest first).
        Use next_cursor for pagination.

        Args:
            experiment_id: Experiment UUID
            cursor: Pagination cursor (use last update ID)
            limit: Maximum results (default 50, max 100)
            update_type: Filter by type (status_change, progress, error)

        Returns:
            UpdateList with updates and pagination cursor
        """
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if update_type:
            params["type"] = update_type
        response = self._client._get(f"/experiments/{experiment_id}/updates", params=params)
        return UpdateList(**response)


class TargetsAPI:
    """Targets endpoint methods."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def get(self, target_id: str) -> TargetInfo:
        """Get target details by ID.

        Args:
            target_id: Target UUID from catalog

        Returns:
            TargetInfo with full target details
        """
        response = self._client._get(f"/targets/{target_id}")
        return TargetInfo(**response)

    def list(self, *, page: int = 1, per_page: int = 50) -> TargetList:
        """List available targets from catalog.

        Args:
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            TargetList with targets and pagination info
        """
        response = self._client._get("/targets", params={"page": page, "per_page": per_page})
        return TargetList(**response)

    def search(self, query: str, *, limit: int = 50) -> TargetList:
        """Search targets by name/description.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            TargetList with matching targets
        """
        response = self._client._get("/targets", params={"search": query, "per_page": limit})
        return TargetList(**response)


class FoundryClient:
    """Low-level client for Foundry Public API.

    Features:
    - Exponential backoff retry for 429 and 5xx errors
    - Request correlation IDs for debugging
    - Structured error handling with request context

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
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = FOUNDRY_API_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize Foundry client.

        Args:
            api_key: Foundry API key
            base_url: API base URL (defaults to production)
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
            return response.json()

        # Try to parse error body
        try:
            body = response.json()
        except Exception:
            body = {"error": response.text}

        # Map status codes to exceptions with full context
        if response.status_code == 401:
            raise AuthenticationError("Invalid API key")

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


# =============================================================================
# Internal API Client
# =============================================================================


class InternalExperimentsAPI(ExperimentsAPI):
    """Experiments API with internal-only methods."""

    def cost_estimate(
        self,
        experiment_spec: ExperimentSpec | dict[str, Any],
    ) -> dict[str, Any]:
        """Estimate experiment cost without creating it.

        Calculates the estimated cost for an experiment based on the spec.
        Useful for previewing costs before submission.

        Note: This endpoint is only available on the internal API.

        Args:
            experiment_spec: Experiment specification (same format as create)

        Returns:
            APICostEstimateResponse with breakdown or incomplete estimate.
            Use APICostEstimateResponse.from_api(response) to parse.

        Example:
            from adaptyv.types.internal import APICostEstimateResponse

            response = client.experiments.cost_estimate({
                "experiment_type": "screening",
                "target_id": "...",
                "sequences": {"seq1": "MVKVG..."},
            })
            estimate = APICostEstimateResponse.from_api(response)

            if estimate.is_complete:
                print(f"Total: ${estimate.total_cents / 100:.2f}")
            else:
                print(f"Assay cost: ${estimate.assay_subtotal_cents / 100:.2f}")
                print(f"Materials: {estimate.incomplete.materials_unavailable.reason}")
        """
        if isinstance(experiment_spec, dict):
            experiment_spec = ExperimentSpec(**experiment_spec)

        payload = {"experiment_spec": experiment_spec.model_dump(exclude_none=True)}
        return self._client._post("/experiments/costestimate", payload)


class InternalFoundryClient(FoundryClient):
    """Internal API client for Adaptyv Foundry.

    Inherits all public API endpoints from FoundryClient.
    Uses the internal API URL by default.

    The internal API has additional endpoints not available in the public API:
    - /experiments/costestimate - Estimate experiment cost
    - /experiments/{id}/results - Get experiment results
    - /results - List all results
    - /sequences - Sequence management
    - /organizations - Organization management
    - /users - User management
    - /tokens - Token management

    These can be added as methods to this class when needed.

    Usage:
        # Automatic via settings
        os.environ["ADAPTYV_API_TYPE"] = "internal"
        client = get_client()  # Returns InternalFoundryClient

        # Explicit
        client = InternalFoundryClient(api_key="...")
    """

    # Override type hint for experiments to include cost_estimate method
    experiments: InternalExperimentsAPI

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = FOUNDRY_API_INTERNAL_URL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        retry_config: RetryConfig | None = None,
    ):
        """Initialize Internal Foundry client.

        Args:
            api_key: Foundry API key (internal token)
            base_url: API base URL (defaults to internal API)
            timeout: Request timeout in seconds
            retries: Number of retries for connection failures
            retry_config: Configuration for application-level retry with backoff
        """
        super().__init__(
            api_key,
            base_url=base_url,
            timeout=timeout,
            retries=retries,
            retry_config=retry_config,
        )
        # Replace with internal experiments API
        self.experiments = InternalExperimentsAPI(self)

    def __enter__(self) -> InternalFoundryClient:
        return self


# =============================================================================
# Mock Client for Testing/CI
# =============================================================================


class MockExperimentsAPI:
    """Mock experiments endpoint for testing without API calls."""

    def list(self) -> ExpList:
        """Return empty experiment list."""
        return ExpList(experiments=[])

    def create(
        self,
        name: str,
        experiment_spec: ExperimentSpec | dict[str, Any],
        *,
        organization_id: str | None = None,
        webhook_url: str | None = None,
        experiment_id: str | None = None,
    ) -> CreateExpResponse:
        """Return mock experiment ID."""
        return CreateExpResponse(experiment_id=experiment_id or "mock-exp-001")

    def get(self, experiment_id: str) -> ExpInfo:
        """Return mock experiment info."""
        return ExpInfo(
            id=experiment_id,
            name="Mock Experiment",
            code="MOCK-001",
            status=ExperimentStatus.waiting_for_confirmation,
            experiment_spec=ExperimentSpec(experiment_type=ExperimentType.screening),
            created_at="2024-01-01T00:00:00Z",
            results_status=ResultsStatus.none,
            experiment_url=f"https://foundry.adaptyvbio.com/exp/{experiment_id}",
        )

    def confirm(self, experiment_id: str) -> ExperimentConfirmationResponse:
        """Return mock confirmation response."""
        return ExperimentConfirmationResponse(
            experiment_id=experiment_id,
            status="confirmed",
            confirmed_at="2024-01-01T00:00:00Z",
            stripe_invoice_id=None,
            stripe_invoice_url=None,
        )

    def get_quote(self, experiment_id: str) -> ExperimentQuoteResponse:
        """Return mock quote response."""
        return ExperimentQuoteResponse(
            experiment_id=experiment_id,
            quote_id="qt_mock123",
            amount_subtotal=9900,
            amount_total=9900,
            currency="usd",
            status="open",
            expires_at="2024-01-08T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )

    def get_invoice(self, experiment_id: str) -> ExperimentInvoiceResponse:
        """Return mock invoice response."""
        return ExperimentInvoiceResponse(
            experiment_id=experiment_id,
            invoice_id="inv_mock123",
            invoice_url="https://invoice.stripe.com/mock",
            status="open",
        )

    def list_updates(
        self,
        experiment_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
        update_type: str | None = None,
    ) -> UpdateList:
        """Return mock updates list."""
        return UpdateList(
            updates=[],
            next_cursor=None,
        )


class MockTargetsAPI:
    """Mock targets endpoint for testing without API calls."""

    def get(self, target_id: str) -> TargetInfo:
        """Return mock target info."""
        return TargetInfo(
            id=target_id,
            name="Mock Target",
            vendor_name="MockVendor",
            catalog_number="MOCK-001",
        )

    def list(self, *, page: int = 1, per_page: int = 50) -> TargetList:
        """Return mock target list."""
        return TargetList(
            targets=[
                TargetListItem(
                    id="mock-target-001",
                    name="Mock Target",
                    vendor_name="MockVendor",
                    catalog_number="MOCK-001",
                )
            ],
            total=1,
            page=page,
            per_page=per_page,
        )

    def search(self, query: str, *, limit: int = 50) -> TargetList:
        """Return mock search results."""
        return self.list(per_page=limit)


class MockFoundryClient:
    """Mock client for testing without real API calls.

    Enabled via ADAPTYV_MOCK_MODE=1 environment variable.
    Returns predictable mock responses for all API methods.

    Usage:
        # Set env var before importing
        os.environ["ADAPTYV_MOCK_MODE"] = "1"

        from adaptyv.client.foundry import get_client
        client = get_client()  # Returns MockFoundryClient

        # All operations return mock data
        exp = client.experiments.create("Test", {...})
        client.experiments.confirm(exp.experiment_id)
    """

    def __init__(self, api_key: str = "mock-api-key", **kwargs: Any):
        """Initialize mock client (api_key is ignored)."""
        self._base_url = "https://mock.foundry.api"
        self.experiments = MockExperimentsAPI()
        self.targets = MockTargetsAPI()

    def close(self) -> None:
        """No-op for mock client."""
        pass

    def __enter__(self) -> MockFoundryClient:
        return self

    def __exit__(self, *args: Any) -> None:
        pass
