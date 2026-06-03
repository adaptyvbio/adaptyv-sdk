"""Pagination envelopes and list-item models for Foundry list endpoints.

The deployed Foundry spec returns every list response as an anonymous inline
object ``{items, total, count, offset}`` whose item schema is also inline, so
``datamodel-codegen`` cannot emit named models for them. This module supplies
the missing named layer by hand: a single generic :class:`Paginated` envelope
plus one item model per list endpoint, mirroring the spec's inline schemas.

These models are stable and hand-maintained; they are intentionally kept out of
``generated.py`` (which ``mise run gen:types`` overwrites). When the spec's list
item schemas change, update the item models here to match.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from adaptyv.types.generated import (
    CustomTargetRequestStatus,
    ExperimentStatus,
    ExperimentType,
    ResultsStatus,
    ResultSummary,
    StripeQuoteStatus,
)

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    """Generic offset-paginated list envelope.

    Mirrors the inline list response shape shared by every Foundry list
    endpoint. The page of records is carried under ``items``; ``total`` is the
    full match count, ``count`` the number of records in this page, and
    ``offset`` the page's starting index.

    Parameters
    ----------
    items
        The records on this page.
    total, count, offset
        Pagination counters as returned by the API.
    """

    items: list[T]
    total: int
    count: int
    offset: int


class ExpListItem(BaseModel):
    """One experiment in a ``GET /experiments`` page."""

    id: str
    code: str
    experiment_url: str
    status: ExperimentStatus
    results_status: ResultsStatus
    name: str | None = None
    experiment_type: ExperimentType | None = None
    stripe_quote_url: str | None = None
    stripe_invoice_url: str | None = None


class TargetListItem(BaseModel):
    """One target in a ``GET /targets`` page.

    ``details`` and ``pricing`` are populated only when the list is requested
    with ``detailed=true``; their shapes vary, so they are left untyped here.
    """

    id: str
    name: str
    vendor_name: str
    catalog_number: str
    url: str
    uniprot_id: str | None = None
    details: Any = None
    pricing: Any = None


class UpdateListItem(BaseModel):
    """One update event in a ``GET /updates`` page."""

    id: str
    name: str
    experiment_id: str
    experiment_code: str
    timestamp: str


class SequenceListItem(BaseModel):
    """One sequence in a ``GET /sequences`` page.

    Carries a truncated ``aa_preview``; fetch the detail endpoint for the full
    amino-acid string.
    """

    id: str
    length: int
    experiment_id: str
    experiment_code: str
    is_control: bool
    created_at: str
    aa_preview: str | None = None
    name: str | None = None


class ResultListItem(BaseModel):
    """One result in a ``GET /results`` page."""

    id: str
    title: str
    experiment_id: str
    result_type: str
    metadata: Any
    summary: list[ResultSummary]
    created_at: str
    data_package_url: str | None = None


class QuoteListItem(BaseModel):
    """One quote in a ``GET /quotes`` page (a flatter shape than ``QuoteInfo``)."""

    id: str
    quote_number: str
    organization_id: str
    amount_cents: int
    currency: str
    status: StripeQuoteStatus
    stripe_quote_url: str
    valid_until: str
    created_at: str


class TokenListItem(BaseModel):
    """One API token in a ``GET /tokens`` page."""

    id: str
    name: str
    kind: str
    created_at: str
    token_type: str | None = None
    parent_token_id: str | None = None
    root_token_id: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    attenuation_spec: Any = None


class CustomTargetRequestListItem(BaseModel):
    """One custom-target request in a ``GET /targets/request-custom`` page."""

    id: str
    name: str
    product_id: str
    status: CustomTargetRequestStatus
    created_at: str


# Concrete envelope aliases, one per list endpoint. Each is callable as a
# pydantic model, e.g. ``SequenceList(**response)``.
ExpList = Paginated[ExpListItem]
TargetList = Paginated[TargetListItem]
UpdateList = Paginated[UpdateListItem]
SequenceList = Paginated[SequenceListItem]
ResultList = Paginated[ResultListItem]
QuoteList = Paginated[QuoteListItem]
TokenList = Paginated[TokenListItem]
CustomTargetRequestList = Paginated[CustomTargetRequestListItem]
