"""Regression tests pinning the SDK to the deployed Foundry contract (0.0.2).

These tests guard the parts of the client most likely to drift from the live
spec: endpoint paths, the cursor-free update feed, the ``items`` list envelopes,
offset pagination, and the enum members. They are respx-mocked and require no
network, so they run in the fast suite (neither ``slow`` nor ``integration``).

The client ``base_url`` already carries the ``/api/v1`` prefix, so a spec path
``/api/v1/experiments/cost-estimate`` is reached as ``/experiments/cost-estimate``
from the SDK. Mocks use the full ``https://api.test.com/api/v1/...`` URL so the
assertions exercise the prefix end to end.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from adaptyv.client.foundry import FoundryClient
from adaptyv.types.generated import (
    ExperimentType,
    FeedbackType,
    QuoteRejectionReason,
    SequenceType,
)

BASE = "https://api.test.com/api/v1"

# Detail responses carry UUID-typed ids; reuse fixed UUIDs where one is needed.
EXP_UUID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def client() -> FoundryClient:
    """Client whose base URL includes the /api/v1 prefix, matching production."""
    return FoundryClient(api_key="test-key", base_url=BASE)


class TestEndpointPaths:
    """Guard the endpoint paths that previously pointed at non-existent routes."""

    @respx.mock
    def test_cost_estimate_hits_hyphenated_path(self, client: FoundryClient) -> None:
        """Given a cost-estimate call, the POST must target /api/v1/experiments/cost-estimate (not costestimate)."""
        route = respx.post(f"{BASE}/experiments/cost-estimate").mock(
            return_value=Response(200, json={"warnings": []})
        )

        client.experiments.cost_estimate(
            {
                "experiment_type": "thermostability",
                "sequences": {"seq1": "MVKVGVNG"},
                "n_replicates": 2,
            }
        )

        assert route.called
        assert str(route.calls[0].request.url).endswith("/api/v1/experiments/cost-estimate")

    @respx.mock
    def test_submit_posts_to_submit_path(self, client: FoundryClient) -> None:
        """Given a draft experiment, submit() must POST to /api/v1/experiments/{id}/submit."""
        route = respx.post(f"{BASE}/experiments/{EXP_UUID}/submit").mock(
            return_value=Response(
                200,
                json={
                    "experiment_id": EXP_UUID,
                    "status": "in_production",
                    "previous_status": "draft",
                    "confirmed_at": "2024-01-01T00:00:00Z",
                },
            )
        )

        client.experiments.submit(EXP_UUID)

        assert route.called
        assert str(route.calls[0].request.url).endswith(f"/api/v1/experiments/{EXP_UUID}/submit")

    @respx.mock
    def test_confirm_quote_posts_to_quote_confirm_path(self, client: FoundryClient) -> None:
        """Given a quoted experiment, confirm_quote() must POST to /api/v1/experiments/{id}/quote/confirm."""
        route = respx.post(f"{BASE}/experiments/{EXP_UUID}/quote/confirm").mock(
            return_value=Response(200, json={"id": EXP_UUID, "status": "accepted"})
        )

        client.experiments.confirm_quote(EXP_UUID, purchase_order_number="PO-42")

        assert route.called
        assert str(route.calls[0].request.url).endswith(
            f"/api/v1/experiments/{EXP_UUID}/quote/confirm"
        )
        body = json.loads(route.calls[0].request.content.decode())
        assert body == {"purchase_order_number": "PO-42"}

    @respx.mock
    def test_modify_uses_http_patch(self, client: FoundryClient) -> None:
        """Given a field change, modify() must issue an HTTP PATCH to /api/v1/experiments/{id}."""
        route = respx.patch(f"{BASE}/experiments/{EXP_UUID}").mock(
            return_value=Response(200, json={"id": EXP_UUID, "updated": True, "message": "ok"})
        )

        client.experiments.modify(EXP_UUID, name="Renamed")

        assert route.called
        assert route.calls[0].request.method == "PATCH"
        assert str(route.calls[0].request.url).endswith(f"/api/v1/experiments/{EXP_UUID}")
        body = json.loads(route.calls[0].request.content.decode())
        assert body == {"name": "Renamed"}


class TestListEnvelopes:
    """Guard the flat ``{items,total,count,offset}`` list shape and offset paging."""

    @respx.mock
    def test_sequences_list_parses_items_envelope(self, client: FoundryClient) -> None:
        """Given an items envelope, sequences.list() must populate SequenceList.items."""
        respx.get(f"{BASE}/sequences").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "id": "seq-001",
                            "name": "Design A",
                            "length": 42,
                            "is_control": False,
                            "experiment_id": "exp-123",
                            "experiment_code": "EXP-2024-001",
                            "created_at": "2024-01-01T00:00:00Z",
                            "aa_preview": "MVKVGVNG",
                        }
                    ],
                    "total": 1,
                    "count": 1,
                    "offset": 0,
                },
            )
        )

        result = client.sequences.list()

        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].length == 42

    @respx.mock
    def test_updates_list_uses_offset_not_cursor(self, client: FoundryClient) -> None:
        """Given limit/offset paging, updates.list() must send those params and no cursor/experiment_id."""
        route = respx.get(f"{BASE}/updates").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "id": "upd-001",
                            "name": "Status changed",
                            "experiment_id": "exp-123",
                            "experiment_code": "EXP-2024-001",
                            "timestamp": "2024-01-01T00:00:00Z",
                        }
                    ],
                    "total": 1,
                    "count": 1,
                    "offset": 5,
                },
            )
        )

        result = client.updates.list(limit=10, offset=5)

        assert len(result.items) == 1
        assert result.offset == 5
        params = route.calls[0].request.url.params
        assert params["limit"] == "10"
        assert params["offset"] == "5"
        assert "cursor" not in params
        assert "experiment_id" not in params


class TestEnumWireValues:
    """Guard the enum members and wire values that changed in the live spec."""

    def test_new_experiment_types_are_valid(self) -> None:
        """Given the 7-member spec, epitope_binning and enzyme_activity must be valid ExperimentType members."""
        assert ExperimentType("epitope_binning") is ExperimentType.epitope_binning
        assert ExperimentType("enzyme_activity") is ExperimentType.enzyme_activity

    def test_sequence_type_scfv_wire_value(self) -> None:
        """Given the cased wire vocabulary, SequenceType('ScFv') must round-trip to the literal 'ScFv'."""
        assert SequenceType("ScFv") is SequenceType.sc_fv
        assert SequenceType.sc_fv.value == "ScFv"


class TestNewResourceSurfaces:
    """Guard that the newly added resource methods reach their spec paths."""

    @respx.mock
    def test_quotes_list_and_actions(self, client: FoundryClient) -> None:
        """Given the quotes resource, list/confirm/reject must target /api/v1/quotes paths with the right verbs."""
        list_route = respx.get(f"{BASE}/quotes").mock(
            return_value=Response(200, json={"items": [], "total": 0, "count": 0, "offset": 0})
        )
        confirm_route = respx.post(f"{BASE}/quotes/q-1/confirm").mock(
            return_value=Response(200, json={"id": "q-1", "status": "accepted"})
        )
        reject_route = respx.post(f"{BASE}/quotes/q-1/reject").mock(
            return_value=Response(200, json={"id": "q-1", "status": "canceled"})
        )

        client.quotes.list()
        client.quotes.confirm("q-1", purchase_order_number="PO-7")
        client.quotes.reject("q-1", reason=QuoteRejectionReason.price, feedback="too high")

        assert list_route.called
        assert confirm_route.called and reject_route.called
        reject_body = json.loads(reject_route.calls[0].request.content.decode())
        assert reject_body["reason"] == "price"
        assert reject_body["feedback"] == "too high"

    @respx.mock
    def test_tokens_list_attenuate_revoke(self, client: FoundryClient) -> None:
        """Given the tokens resource, list/attenuate/revoke must target /api/v1/tokens paths."""
        list_route = respx.get(f"{BASE}/tokens").mock(
            return_value=Response(200, json={"items": [], "total": 0, "count": 0, "offset": 0})
        )
        att_route = respx.post(f"{BASE}/tokens/attenuate").mock(
            return_value=Response(200, json={"id": "t-2", "token": "secret-2"})
        )
        revoke_route = respx.post(f"{BASE}/tokens/revoke").mock(
            return_value=Response(
                200,
                json={
                    "token_id": "t-1",
                    "children_revoked": 0,
                    "revoked_at": "2024-01-01T00:00:00Z",
                },
            )
        )

        client.tokens.list()
        client.tokens.attenuate(token="secret-1", name="child", attenuation={})
        client.tokens.revoke()

        assert list_route.called and att_route.called and revoke_route.called
        # revoke takes no body
        assert revoke_route.calls[0].request.content in (b"", b"{}")

    @respx.mock
    def test_feedback_submit(self, client: FoundryClient) -> None:
        """Given the feedback resource, submit() must POST to /api/v1/feedback/submit with the feedback_type."""
        route = respx.post(f"{BASE}/feedback/submit").mock(
            return_value=Response(200, json={"message": "thanks", "reference": "fb-1"})
        )

        result = client.feedback.submit(
            feedback_type=FeedbackType.bug_report,
            request_uuid=EXP_UUID,
            human_note="something broke",
        )

        assert route.called
        assert result.reference == "fb-1"
        body = json.loads(route.calls[0].request.content.decode())
        assert body["feedback_type"] == "bug_report"
        assert body["request_uuid"] == EXP_UUID

    @respx.mock
    def test_info_health_endpoints(self, client: FoundryClient) -> None:
        """Given the info resource, health()/health_db() must target /api/v1/info/health and /info/health-db."""
        health_route = respx.get(f"{BASE}/info/health").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        db_route = respx.get(f"{BASE}/info/health-db").mock(
            return_value=Response(200, json={"status": "ok", "db": "ok"})
        )

        assert client.info.health().status == "ok"
        assert client.info.health_db().db == "ok"
        assert health_route.called and db_route.called

    @respx.mock
    def test_get_quote_pdf_returns_bytes(self, client: FoundryClient) -> None:
        """Given a quote PDF endpoint, get_quote_pdf() must return the raw response bytes."""
        pdf_bytes = b"%PDF-1.7 fake quote"
        respx.get(f"{BASE}/experiments/{EXP_UUID}/quote/pdf").mock(
            return_value=Response(
                200, content=pdf_bytes, headers={"Content-Type": "application/pdf"}
            )
        )

        result = client.experiments.get_quote_pdf(EXP_UUID)

        assert result == pdf_bytes
