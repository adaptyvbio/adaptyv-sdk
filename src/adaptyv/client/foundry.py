"""Foundry API client for Adaptyv Lab SDK.

Targets Foundry contract :data:`FOUNDRY_SPEC_VERSION`. All paths below omit the
``/api/v1`` prefix because the configured ``base_url`` already carries it.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

import httpx

from adaptyv.config import (
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    FOUNDRY_SPEC_VERSION,
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
from adaptyv.types import (
    AttenuateTokenRequest,
    AttenuateTokenResponse,
    AttenuationSpec,
    ConfirmQuoteRequest,
    ConfirmQuoteResponse,
    CostEstimateResponse,
    CreateCustomTargetRequest,
    CreateCustomTargetResponse,
    CreateExpRequest,
    CreateExpResponse,
    CustomTargetRequestInfo,
    CustomTargetRequestList,
    ExperimentConfirmationResponse,
    ExperimentInvoiceResponse,
    ExperimentQuoteResponse,
    ExperimentSpec,
    ExperimentType,
    ExpInfo,
    ExpList,
    FeedbackType,
    HealthDbResponse,
    HealthResponse,
    ModifyExpRequest,
    ModifyExpResponse,
    QuoteInfo,
    QuoteList,
    QuoteRejectionReason,
    RejectQuoteRequest,
    RejectQuoteResponse,
    ResultInfo,
    ResultList,
    RevokeTokenResponse,
    SequenceAddResponse,
    SequenceEntry,
    SequenceInfo,
    SequenceList,
    SubmitFeedbackRequest,
    SubmitFeedbackResponse,
    TargetInfo,
    TargetList,
    TokenList,
    UpdateList,
)

logger = logging.getLogger("adaptyv")

__all__ = [
    "FOUNDRY_SPEC_VERSION",
    "FoundryClient",
    "FoundryClientProtocol",
    "ExperimentsAPI",
    "TargetsAPI",
    "UpdatesAPI",
    "SequencesAPI",
    "ResultsAPI",
    "QuotesAPI",
    "TokensAPI",
    "FeedbackAPI",
    "InfoAPI",
    "get_client",
]


@runtime_checkable
class ExperimentsAPIProtocol(Protocol):
    """Protocol for experiments API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> ExpList: ...
    def create(
        self,
        name: str,
        experiment_spec: ExperimentSpec | dict[str, Any],
        *,
        organization_id: str | None = None,
        webhook_url: str | None = None,
        confirmed: bool = False,
        auto_link_material: bool = False,
    ) -> CreateExpResponse: ...
    def get(self, experiment_id: str) -> ExpInfo: ...
    def cost_estimate(
        self, experiment_spec: ExperimentSpec | dict[str, Any]
    ) -> CostEstimateResponse: ...
    def get_quote(self, experiment_id: str) -> ExperimentQuoteResponse: ...
    def get_invoice(self, experiment_id: str) -> ExperimentInvoiceResponse: ...
    def submit(self, experiment_id: str) -> ExperimentConfirmationResponse: ...
    def confirm_quote(
        self,
        experiment_id: str,
        *,
        notes: str | None = None,
        purchase_order_number: str | None = None,
    ) -> ConfirmQuoteResponse: ...
    def modify(
        self,
        experiment_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        target_id: str | None = None,
        antigen_concentrations: Sequence[float] | None = None,
        n_replicates: int | None = None,
        parameters: Any | None = None,
        sequences: Sequence[SequenceEntry | dict[str, Any]] | None = None,
        webhook_url: str | None = None,
    ) -> ModifyExpResponse: ...
    def get_results(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> ResultList: ...
    def get_sequences(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        sort: str | None = None,
    ) -> SequenceList: ...
    def list_updates(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        sort: str | None = None,
    ) -> UpdateList: ...
    def get_quote_pdf(self, experiment_id: str) -> bytes: ...


@runtime_checkable
class TargetsAPIProtocol(Protocol):
    """Protocol for targets API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        sort: str | None = None,
        selfservice_only: bool = False,
        show_conjugated: bool | None = None,
        detailed: bool | None = None,
    ) -> TargetList: ...
    def search(
        self,
        query: str,
        *,
        limit: int = 50,
        offset: int = 0,
        selfservice_only: bool = False,
        sort: str | None = None,
    ) -> TargetList: ...
    def get(self, target_id: str) -> TargetInfo: ...
    def list_custom_requests(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        sort: str | None = None,
    ) -> CustomTargetRequestList: ...
    def create_custom_request(
        self,
        *,
        name: str,
        product_id: str,
        molecular_weight: float | None = None,
        note: str | None = None,
        pdb_file: str | None = None,
        pdb_id: str | None = None,
        product_url: str | None = None,
        sequence: str | None = None,
        vendor: str | None = None,
    ) -> CreateCustomTargetResponse: ...
    def get_custom_request(self, request_id: str) -> CustomTargetRequestInfo: ...


@runtime_checkable
class UpdatesAPIProtocol(Protocol):
    """Protocol for global updates API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        sort: str | None = None,
    ) -> UpdateList: ...


@runtime_checkable
class SequencesAPIProtocol(Protocol):
    """Protocol for sequences API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        sort: str | None = None,
        experiment_id: str | None = None,
    ) -> SequenceList: ...
    def create(
        self,
        experiment_code: str,
        sequences: Sequence[SequenceEntry | dict[str, Any]],
    ) -> SequenceAddResponse: ...
    def get(self, sequence_id: str) -> SequenceInfo: ...


@runtime_checkable
class ResultsAPIProtocol(Protocol):
    """Protocol for results API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> ResultList: ...
    def get(self, result_id: str) -> ResultInfo: ...


@runtime_checkable
class QuotesAPIProtocol(Protocol):
    """Protocol for quotes API."""

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        sort: str | None = None,
    ) -> QuoteList: ...
    def get(self, quote_id: str) -> QuoteInfo: ...
    def confirm(
        self,
        quote_id: str,
        *,
        notes: str | None = None,
        purchase_order_number: str | None = None,
    ) -> ConfirmQuoteResponse: ...
    def reject(
        self,
        quote_id: str,
        *,
        reason: QuoteRejectionReason,
        feedback: str | None = None,
    ) -> RejectQuoteResponse: ...


@runtime_checkable
class TokensAPIProtocol(Protocol):
    """Protocol for tokens API."""

    def list(self, *, limit: int = 50, offset: int = 0) -> TokenList: ...
    def attenuate(
        self,
        *,
        token: str,
        name: str,
        attenuation: AttenuationSpec | dict[str, Any],
        attenuated_parent_token_id: str | None = None,
    ) -> AttenuateTokenResponse: ...
    def revoke(self) -> RevokeTokenResponse: ...


@runtime_checkable
class FeedbackAPIProtocol(Protocol):
    """Protocol for feedback API."""

    def submit(
        self,
        *,
        feedback_type: FeedbackType,
        request_uuid: str,
        human_note: str | None = None,
        json_body: Any | None = None,
        title: str | None = None,
    ) -> SubmitFeedbackResponse: ...


@runtime_checkable
class InfoAPIProtocol(Protocol):
    """Protocol for info/health API."""

    def health(self) -> HealthResponse: ...
    def health_db(self) -> HealthDbResponse: ...


@runtime_checkable
class FoundryClientProtocol(Protocol):
    """Protocol that all Foundry clients must implement."""

    experiments: ExperimentsAPIProtocol
    targets: TargetsAPIProtocol
    updates: UpdatesAPIProtocol
    sequences: SequencesAPIProtocol
    results: ResultsAPIProtocol
    quotes: QuotesAPIProtocol
    tokens: TokensAPIProtocol
    feedback: FeedbackAPIProtocol
    info: InfoAPIProtocol

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
        filter: str | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> ExpList:
        """List experiments.

        Parameters
        ----------
        limit, offset
            Offset-pagination window.
        filter
            Filter s-expression (e.g. ``equ(status)=draft``).
        search
            Case-insensitive search term.
        sort
            Sort spec (e.g. ``-created_at``).

        Returns
        -------
        ExpList
            One page of experiments.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if filter is not None:
            params["filter"] = filter
        if search is not None:
            params["search"] = search
        if sort is not None:
            params["sort"] = sort
        response = self._client._get("/experiments", params=params)
        return ExpList(**response)

    def create(
        self,
        name: str,
        experiment_spec: ExperimentSpec | dict[str, Any],
        *,
        organization_id: str | None = None,
        webhook_url: str | None = None,
        confirmed: bool = False,
        auto_link_material: bool = False,
    ) -> CreateExpResponse:
        """Create a new experiment.

        Parameters
        ----------
        name
            Human-readable experiment name.
        experiment_spec
            Experiment specification (type, target, sequences).
        organization_id
            Organization ID (for multi-org accounts).
        webhook_url
            URL for status update callbacks.
        confirmed
            If True, skip draft and submit directly.
        auto_link_material
            If True, auto-link inventory material.

        Returns
        -------
        CreateExpResponse
            Response carrying ``experiment_id``.
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
        )

        payload = request.model_dump(mode="json", exclude_none=True)
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

    def cost_estimate(
        self,
        experiment_spec: ExperimentSpec | dict[str, Any],
    ) -> CostEstimateResponse:
        """Estimate experiment cost without creating it.

        Parameters
        ----------
        experiment_spec
            Experiment specification to price.

        Returns
        -------
        CostEstimateResponse
            Itemized cost breakdown.
        """
        if isinstance(experiment_spec, dict):
            experiment_spec = ExperimentSpec(**experiment_spec)

        payload = {
            "experiment_spec": experiment_spec.model_dump(
                mode="json", exclude_none=True
            )
        }
        response = self._client._post("/experiments/cost-estimate", payload)
        return CostEstimateResponse(**response)

    def get_quote(self, experiment_id: str) -> ExperimentQuoteResponse:
        """Get experiment quote details."""
        response = self._client._get(f"/experiments/{experiment_id}/quote")
        return ExperimentQuoteResponse(**response)

    def get_invoice(self, experiment_id: str) -> ExperimentInvoiceResponse:
        """Get experiment invoice details."""
        response = self._client._get(f"/experiments/{experiment_id}/invoice")
        return ExperimentInvoiceResponse(**response)

    def submit(self, experiment_id: str) -> ExperimentConfirmationResponse:
        """Submit a draft experiment for processing."""
        response = self._client._post(f"/experiments/{experiment_id}/submit", {})
        return ExperimentConfirmationResponse(**response)

    def confirm_quote(
        self,
        experiment_id: str,
        *,
        notes: str | None = None,
        purchase_order_number: str | None = None,
    ) -> ConfirmQuoteResponse:
        """Confirm the quote attached to an experiment.

        Parameters
        ----------
        notes
            Reserved for future use; accepted but not acted upon.
        purchase_order_number
            Purchase order number from your organization.
        """
        request = ConfirmQuoteRequest(
            notes=notes, purchase_order_number=purchase_order_number
        )
        payload = request.model_dump(mode="json", exclude_none=True)
        response = self._client._post(
            f"/experiments/{experiment_id}/quote/confirm", payload
        )
        return ConfirmQuoteResponse(**response)

    def modify(
        self,
        experiment_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        target_id: str | None = None,
        antigen_concentrations: Sequence[float] | None = None,
        n_replicates: int | None = None,
        parameters: Any | None = None,
        sequences: Sequence[SequenceEntry | dict[str, Any]] | None = None,
        webhook_url: str | None = None,
    ) -> ModifyExpResponse:
        """Modify a not-yet-fulfilled experiment.

        Mirrors :class:`ModifyExpRequest`. Only the fields you pass are sent;
        unset fields leave the corresponding server-side value untouched.
        """
        seq_entries: list[SequenceEntry] | None = None
        if sequences is not None:
            seq_entries = [
                s if isinstance(s, SequenceEntry) else SequenceEntry(**s)
                for s in sequences
            ]
        request = ModifyExpRequest(
            name=name,
            description=description,
            target_id=target_id,
            antigen_concentrations=(
                list(antigen_concentrations)
                if antigen_concentrations is not None
                else None
            ),
            n_replicates=n_replicates,
            parameters=parameters,
            sequences=seq_entries,
            webhook_url=webhook_url,
        )
        payload = request.model_dump(mode="json", exclude_none=True)
        response = self._client._patch(f"/experiments/{experiment_id}", payload)
        return ModifyExpResponse(**response)

    def get_results(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> ResultList:
        """Get results for a specific experiment."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if filter is not None:
            params["filter"] = filter
        if search is not None:
            params["search"] = search
        if sort is not None:
            params["sort"] = sort
        response = self._client._get(
            f"/experiments/{experiment_id}/results", params=params
        )
        return ResultList(**response)

    def get_sequences(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        sort: str | None = None,
    ) -> SequenceList:
        """List sequences belonging to a specific experiment."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search is not None:
            params["search"] = search
        if sort is not None:
            params["sort"] = sort
        response = self._client._get(
            f"/experiments/{experiment_id}/sequences", params=params
        )
        return SequenceList(**response)

    def list_updates(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        sort: str | None = None,
    ) -> UpdateList:
        """List status updates for a specific experiment."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if filter is not None:
            params["filter"] = filter
        if sort is not None:
            params["sort"] = sort
        response = self._client._get(
            f"/experiments/{experiment_id}/updates", params=params
        )
        return UpdateList(**response)

    def get_quote_pdf(self, experiment_id: str) -> bytes:
        """Fetch the experiment's quote as a raw PDF byte string."""
        return self._client._get_bytes(f"/experiments/{experiment_id}/quote/pdf")


class TargetsAPI:
    """Targets endpoint methods."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        sort: str | None = None,
        selfservice_only: bool = False,
        show_conjugated: bool | None = None,
        detailed: bool | None = None,
    ) -> TargetList:
        """List available targets.

        Parameters
        ----------
        limit, offset
            Offset-pagination window.
        search
            Case-insensitive search term.
        sort
            Sort spec.
        selfservice_only
            If True, restrict to self-service targets.
        show_conjugated
            If set, include or exclude conjugated targets.
        detailed
            If True, populate per-target ``details`` and ``pricing``.

        Returns
        -------
        TargetList
            One page of targets.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search is not None:
            params["search"] = search
        if sort is not None:
            params["sort"] = sort
        if selfservice_only:
            params["selfservice_only"] = "true"
        if show_conjugated is not None:
            params["show_conjugated"] = "true" if show_conjugated else "false"
        if detailed is not None:
            params["detailed"] = "true" if detailed else "false"
        response = self._client._get("/targets", params=params)
        return TargetList(**response)

    def search(
        self,
        query: str,
        *,
        limit: int = 50,
        offset: int = 0,
        selfservice_only: bool = False,
        sort: str | None = None,
    ) -> TargetList:
        """Search targets by name/description.

        Thin wrapper over :meth:`list` with ``search`` set to ``query``.
        """
        return self.list(
            limit=limit,
            offset=offset,
            search=query,
            sort=sort,
            selfservice_only=selfservice_only,
        )

    def get(self, target_id: str) -> TargetInfo:
        """Get target by ID."""
        response = self._client._get(f"/targets/{target_id}")
        return TargetInfo(**response)

    def list_custom_requests(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        sort: str | None = None,
    ) -> CustomTargetRequestList:
        """List custom-target requests."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if filter is not None:
            params["filter"] = filter
        if sort is not None:
            params["sort"] = sort
        response = self._client._get("/targets/request-custom", params=params)
        return CustomTargetRequestList(**response)

    def create_custom_request(
        self,
        *,
        name: str,
        product_id: str,
        molecular_weight: float | None = None,
        note: str | None = None,
        pdb_file: str | None = None,
        pdb_id: str | None = None,
        product_url: str | None = None,
        sequence: str | None = None,
        vendor: str | None = None,
    ) -> CreateCustomTargetResponse:
        """Request a custom target.

        Mirrors :class:`CreateCustomTargetRequest`; ``name`` and ``product_id``
        are required.
        """
        request = CreateCustomTargetRequest(
            name=name,
            product_id=product_id,
            molecular_weight=molecular_weight,
            note=note,
            pdb_file=pdb_file,
            pdb_id=pdb_id,
            product_url=product_url,
            sequence=sequence,
            vendor=vendor,
        )
        payload = request.model_dump(mode="json", exclude_none=True)
        response = self._client._post("/targets/request-custom", payload)
        return CreateCustomTargetResponse(**response)

    def get_custom_request(self, request_id: str) -> CustomTargetRequestInfo:
        """Get a custom-target request by ID."""
        response = self._client._get(f"/targets/request-custom/{request_id}")
        return CustomTargetRequestInfo(**response)


class UpdatesAPI:
    """Global updates endpoint for the cross-experiment update feed."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        sort: str | None = None,
    ) -> UpdateList:
        """List updates across all accessible experiments.

        Parameters
        ----------
        limit, offset
            Offset-pagination window.
        filter
            Filter s-expression; narrow to one experiment with
            ``equ(experiment_id)=<uuid>``.
        sort
            Sort spec.
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if filter is not None:
            params["filter"] = filter
        if sort is not None:
            params["sort"] = sort
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
        search: str | None = None,
        sort: str | None = None,
        experiment_id: str | None = None,
    ) -> SequenceList:
        """List sequences from accessible experiments."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search is not None:
            params["search"] = search
        if sort is not None:
            params["sort"] = sort
        if experiment_id is not None:
            params["experiment_id"] = experiment_id
        response = self._client._get("/sequences", params=params)
        return SequenceList(**response)

    def create(
        self,
        experiment_code: str,
        sequences: Sequence[SequenceEntry | dict[str, Any]],
    ) -> SequenceAddResponse:
        """Append sequences to a draft experiment.

        Parameters
        ----------
        experiment_code
            Human-readable experiment code (e.g. ``"PROJ-001"``).
        sequences
            Sequences to add.

        Returns
        -------
        SequenceAddResponse
            Added count and new sequence IDs.
        """
        seq_entries = [
            s if isinstance(s, SequenceEntry) else SequenceEntry(**s) for s in sequences
        ]
        payload = {
            "experiment_code": experiment_code,
            "sequences": [
                s.model_dump(mode="json", exclude_none=True) for s in seq_entries
            ],
        }
        response = self._client._post("/sequences", payload)
        return SequenceAddResponse(**response)

    def get(self, sequence_id: str) -> SequenceInfo:
        """Get full details for a specific sequence."""
        response = self._client._get(f"/sequences/{sequence_id}")
        return SequenceInfo(**response)


class ResultsAPI:
    """Results endpoint for accessing experiment results."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        search: str | None = None,
        sort: str | None = None,
    ) -> ResultList:
        """List completed analysis results."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if filter is not None:
            params["filter"] = filter
        if search is not None:
            params["search"] = search
        if sort is not None:
            params["sort"] = sort
        response = self._client._get("/results", params=params)
        return ResultList(**response)

    def get(self, result_id: str) -> ResultInfo:
        """Get full details for a specific result."""
        response = self._client._get(f"/results/{result_id}")
        return ResultInfo(**response)


class QuotesAPI:
    """Quotes endpoint for inspecting and acting on quotes."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        filter: str | None = None,
        sort: str | None = None,
    ) -> QuoteList:
        """List quotes."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if filter is not None:
            params["filter"] = filter
        if sort is not None:
            params["sort"] = sort
        response = self._client._get("/quotes", params=params)
        return QuoteList(**response)

    def get(self, quote_id: str) -> QuoteInfo:
        """Get a quote by ID."""
        response = self._client._get(f"/quotes/{quote_id}")
        return QuoteInfo(**response)

    def confirm(
        self,
        quote_id: str,
        *,
        notes: str | None = None,
        purchase_order_number: str | None = None,
    ) -> ConfirmQuoteResponse:
        """Accept a quote, generating an invoice."""
        request = ConfirmQuoteRequest(
            notes=notes, purchase_order_number=purchase_order_number
        )
        payload = request.model_dump(mode="json", exclude_none=True)
        response = self._client._post(f"/quotes/{quote_id}/confirm", payload)
        return ConfirmQuoteResponse(**response)

    def reject(
        self,
        quote_id: str,
        *,
        reason: QuoteRejectionReason,
        feedback: str | None = None,
    ) -> RejectQuoteResponse:
        """Reject a quote.

        Parameters
        ----------
        reason
            Primary rejection reason.
        feedback
            Optional free-text elaboration.
        """
        request = RejectQuoteRequest(reason=reason, feedback=feedback)
        payload = request.model_dump(mode="json", exclude_none=True)
        response = self._client._post(f"/quotes/{quote_id}/reject", payload)
        return RejectQuoteResponse(**response)


class TokensAPI:
    """Tokens endpoint for listing, attenuating, and revoking API tokens."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def list(self, *, limit: int = 50, offset: int = 0) -> TokenList:
        """List API tokens."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        response = self._client._get("/tokens", params=params)
        return TokenList(**response)

    def attenuate(
        self,
        *,
        token: str,
        name: str,
        attenuation: AttenuationSpec | dict[str, Any],
        attenuated_parent_token_id: str | None = None,
    ) -> AttenuateTokenResponse:
        """Mint an attenuated (restricted) child token.

        Parameters
        ----------
        token
            Existing token string to attenuate.
        name
            Display label for the new attenuated token.
        attenuation
            Restrictions to apply.
        attenuated_parent_token_id
            For chained attenuation, the ``id`` of the parent attenuated record.
        """
        if isinstance(attenuation, dict):
            attenuation = AttenuationSpec(**attenuation)
        request = AttenuateTokenRequest(
            token=token,
            name=name,
            attenuation=attenuation,
            attenuated_parent_token_id=attenuated_parent_token_id,
        )
        payload = request.model_dump(mode="json", exclude_none=True)
        response = self._client._post("/tokens/attenuate", payload)
        return AttenuateTokenResponse(**response)

    def revoke(self) -> RevokeTokenResponse:
        """Revoke the authenticating token and all its descendants.

        The endpoint takes no body; it acts on the token used to authenticate
        this request.
        """
        response = self._client._post("/tokens/revoke", {})
        return RevokeTokenResponse(**response)


class FeedbackAPI:
    """Feedback endpoint for submitting structured feedback."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def submit(
        self,
        *,
        feedback_type: FeedbackType,
        request_uuid: str,
        human_note: str | None = None,
        json_body: Any | None = None,
        title: str | None = None,
    ) -> SubmitFeedbackResponse:
        """Submit feedback tied to a prior request.

        Parameters
        ----------
        feedback_type
            Feedback category.
        request_uuid
            UUID of the request that prompted this feedback.
        human_note
            Optional free-text note.
        json_body
            Optional structured details.
        title
            Optional short title.
        """
        request = SubmitFeedbackRequest(
            feedback_type=feedback_type,
            request_uuid=request_uuid,
            human_note=human_note,
            json_body=json_body,
            title=title,
        )
        payload = request.model_dump(mode="json", exclude_none=True)
        response = self._client._post("/feedback/submit", payload)
        return SubmitFeedbackResponse(**response)


class InfoAPI:
    """Info endpoint for service and database health checks."""

    def __init__(self, client: FoundryClient):
        self._client = client

    def health(self) -> HealthResponse:
        """Check overall service health."""
        response = self._client._get("/info/health")
        return HealthResponse(**response)

    def health_db(self) -> HealthDbResponse:
        """Check database connectivity health."""
        response = self._client._get("/info/health-db")
        return HealthDbResponse(**response)


class FoundryClient:
    """Client for the Adaptyv Foundry API (contract :data:`FOUNDRY_SPEC_VERSION`).

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

        # Submit the draft, then confirm its quote
        client.experiments.submit(exp.experiment_id)
        client.experiments.confirm_quote(exp.experiment_id)

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
        self.quotes = QuotesAPI(self)
        self.tokens = TokensAPI(self)
        self.feedback = FeedbackAPI(self)
        self.info = InfoAPI(self)

    def _generate_correlation_id(self) -> str:
        """Generate a unique correlation ID for request tracking."""
        return f"sdk-{uuid.uuid4().hex[:12]}"

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make GET request with retry logic."""
        return self._request_with_retry("GET", path, params=params)

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make POST request with retry logic."""
        return self._request_with_retry("POST", path, json_data=data)

    def _patch(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make PATCH request with retry logic."""
        return self._request_with_retry("PATCH", path, json_data=data)

    def _get_bytes(self, path: str) -> bytes:
        """Fetch a binary (non-JSON) response body with retry logic."""
        return self._request_bytes_with_retry("GET", path)

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
        response = self._send_with_retry(method, path, params=params, json_data=json_data)
        return cast(dict[str, Any], response.json())

    def _request_bytes_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> bytes:
        """Execute request with retry, returning the raw response body."""
        response = self._send_with_retry(method, path, params=params, json_data=None)
        return response.content

    def _send_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Execute the request with retry, returning the validated raw response.

        Centralizes the retry loop and error mapping. Callers decode the body
        (JSON or bytes) themselves.
        """
        correlation_id = self._generate_correlation_id()
        last_error: APIError | None = None

        for attempt in range(self._retry_config.max_attempts + 1):
            try:
                start_time = time.monotonic()

                # Add correlation ID to headers
                headers = {"X-Correlation-ID": correlation_id}

                response = self._client.request(
                    method,
                    path,
                    params=params,
                    json=json_data if method != "GET" else None,
                    headers=headers,
                )

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

                self._raise_for_status(response, path, correlation_id)
                return response

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

    def _raise_for_status(
        self,
        response: httpx.Response,
        path: str,
        correlation_id: str,
    ) -> None:
        """Raise an appropriate exception for an error response, else return.

        Maps HTTP status codes to the SDK's exception hierarchy with full
        request context. Successful responses (status < 400) return without
        action; the caller decodes the body.
        """
        # Extract request ID from response headers
        request_id = response.headers.get("X-Request-ID") or correlation_id

        if response.status_code < 400:
            return

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
