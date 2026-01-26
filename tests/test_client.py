"""Tests for FoundryClient."""

import pytest
import respx
from httpx import Response

from adaptyv.client.foundry import FoundryClient
from adaptyv.config import RetryConfig
from adaptyv.exceptions import (
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ValidationError,
)


@pytest.fixture
def client() -> FoundryClient:
    """Create test client."""
    return FoundryClient(api_key="test-api-key", base_url="https://api.test.com")


class TestFoundryClientInit:
    """Test client initialization."""

    def test_requires_api_key(self) -> None:
        """Should raise error without API key."""
        with pytest.raises(AuthenticationError):
            FoundryClient(api_key="", base_url="https://api.example.com")

    def test_accepts_api_key(self) -> None:
        """Should accept valid API key."""
        client = FoundryClient(api_key="test-key", base_url="https://api.example.com")
        assert client._client is not None  # Client was created

    def test_accepts_custom_base_url(self) -> None:
        """Should accept custom base URL."""
        client = FoundryClient(api_key="test-key", base_url="https://custom.api.com")
        assert client._base_url == "https://custom.api.com"


class TestDefaultConfig:
    """Test default configuration values."""

    def test_default_api_url(self) -> None:
        """Should have default API URL configured."""
        from adaptyv.config import FOUNDRY_API_URL, AdaptyvConfig

        config = AdaptyvConfig()
        assert config.api_url == FOUNDRY_API_URL
        assert "adaptyvbio.com" in config.api_url  # Generic check, no internal URL


class TestExperimentsAPI:
    """Test experiments endpoint."""

    @respx.mock
    def test_list_experiments(self, client: FoundryClient) -> None:
        """Should list experiments with pagination."""
        respx.get("https://api.test.com/experiments").mock(
            return_value=Response(
                200,
                json={
                    "experiments": [
                        {
                            "id": "exp-123",
                            "name": "Test Exp",
                            "code": "EXP-001",
                            "status": "in_production",
                            "experiment_type": "thermostability",
                            "experiment_url": "https://app.example.com/exp/123",
                            "results_status": "none",
                            "created_at": "2024-01-01T00:00:00Z",
                        }
                    ],
                    "total": 1,
                    "count": 1,
                    "offset": 0,
                },
            )
        )

        result = client.experiments.list(limit=10)

        assert len(result.experiments) == 1
        assert result.experiments[0].id == "exp-123"
        assert result.experiments[0].experiment_type.value == "thermostability"

    @respx.mock
    def test_list_experiments_with_filters(self, client: FoundryClient) -> None:
        """Should pass filter params to API."""
        route = respx.get("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiments": [], "total": 0, "count": 0, "offset": 5})
        )

        client.experiments.list(limit=10, offset=5, status="done", search="test")

        assert route.calls[0].request.url.params["limit"] == "10"
        assert route.calls[0].request.url.params["offset"] == "5"
        assert route.calls[0].request.url.params["status"] == "done"
        assert route.calls[0].request.url.params["search"] == "test"

    @respx.mock
    def test_cost_estimate(self, client: FoundryClient) -> None:
        """Should estimate cost without creating experiment."""
        route = respx.post("https://api.test.com/experiments/costestimate").mock(
            return_value=Response(200, json={"estimated_cost": 500, "currency": "usd"})
        )

        result = client.experiments.cost_estimate(
            {
                "experiment_type": "thermostability",
                "sequences": {"seq1": "MVKVGVNG"},
                "n_replicates": 2,
            }
        )

        assert result["estimated_cost"] == 500
        request_body = route.calls[0].request.content.decode()
        assert "experiment_spec" in request_body

    @respx.mock
    def test_create_experiment(self, client: FoundryClient) -> None:
        """Should create experiment and return ID."""
        respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        # Use thermostability which doesn't require target_id
        result = client.experiments.create(
            name="Test Experiment",
            experiment_spec={
                "experiment_type": "thermostability",
                "sequences": {"seq1": "MVKVGVNG"},
            },
        )

        assert result.experiment_id == "exp-123"

    @respx.mock
    def test_create_experiment_with_webhook(self, client: FoundryClient) -> None:
        """Should include webhook URL in request."""
        route = respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        # Use thermostability which doesn't require target_id
        client.experiments.create(
            name="Test",
            experiment_spec={
                "experiment_type": "thermostability",
                "sequences": {"seq1": "MVKVGVNG"},
            },
            webhook_url="https://webhook.test.com",
        )

        request_body = route.calls[0].request.content.decode()
        assert "webhook.test.com" in request_body

    @respx.mock
    def test_get_experiment(self, client: FoundryClient) -> None:
        """Should get experiment details."""
        respx.get("https://api.test.com/experiments/exp-123").mock(
            return_value=Response(
                200,
                json={
                    "id": "exp-123",
                    "name": "Test",
                    "code": "EXP-001",
                    "status": "waiting_for_confirmation",
                    "experiment_spec": {
                        "experiment_type": "screening",
                        "sequences": {"seq1": "MVKVGVNG"},
                    },
                    "created_at": "2024-01-01T00:00:00Z",
                    "results_status": "none",
                    "experiment_url": "https://app.example.com/exp/123",
                },
            )
        )

        result = client.experiments.get("exp-123")

        assert result.id == "exp-123"
        assert result.status.value == "waiting_for_confirmation"
        assert result.results_status.value == "none"

    @respx.mock
    def test_confirm_experiment(self, client: FoundryClient) -> None:
        """Should confirm experiment and return confirmation details."""
        respx.post("https://api.test.com/experiments/exp-123/confirm").mock(
            return_value=Response(
                200,
                json={
                    "experiment_id": "exp-123",
                    "status": "confirmed",
                    "confirmed_at": "2024-01-01T00:00:00Z",
                },
            )
        )

        result = client.experiments.confirm("exp-123")

        assert result.experiment_id == "exp-123"
        assert result.status == "confirmed"
        assert result.confirmed_at == "2024-01-01T00:00:00Z"

    @respx.mock
    def test_get_quote(self, client: FoundryClient) -> None:
        """Should get experiment quote details."""
        respx.get("https://api.test.com/experiments/exp-123/quote").mock(
            return_value=Response(
                200,
                json={
                    "experiment_id": "exp-123",
                    "quote_id": "qt_abc123",
                    "amount_subtotal": 9900,
                    "amount_total": 9900,
                    "currency": "usd",
                    "status": "open",
                    "expires_at": "2024-01-08T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                    "stripe_quote_url": "https://quote.stripe.com/qt_abc123",
                },
            )
        )

        result = client.experiments.get_quote("exp-123")

        assert result.experiment_id == "exp-123"
        assert result.quote_id == "qt_abc123"
        assert result.amount_total == 9900
        assert result.currency == "usd"
        assert result.status == "open"
        assert result.stripe_quote_url == "https://quote.stripe.com/qt_abc123"

    @respx.mock
    def test_get_invoice(self, client: FoundryClient) -> None:
        """Should get experiment invoice details."""
        respx.get("https://api.test.com/experiments/exp-123/invoice").mock(
            return_value=Response(
                200,
                json={
                    "experiment_id": "exp-123",
                    "invoice_id": "inv_abc123",
                    "invoice_url": "https://invoice.stripe.com/i/acct_123",
                    "status": "open",
                },
            )
        )

        result = client.experiments.get_invoice("exp-123")

        assert result.experiment_id == "exp-123"
        assert result.invoice_id == "inv_abc123"
        assert result.invoice_url == "https://invoice.stripe.com/i/acct_123"
        assert result.status == "open"

    @respx.mock
    def test_list_updates(self, client: FoundryClient) -> None:
        """Should list experiment updates."""
        respx.get("https://api.test.com/experiments/exp-123/updates").mock(
            return_value=Response(
                200,
                json={
                    "updates": [
                        {
                            "id": "upd-001",
                            "experiment_id": "exp-123",
                            "experiment_code": "EXP-2024-001",
                            "name": "Experiment created",
                            "timestamp": "2024-01-01T00:00:00Z",
                        },
                        {
                            "id": "upd-002",
                            "experiment_id": "exp-123",
                            "experiment_code": "EXP-2024-001",
                            "name": "Quote generated",
                            "timestamp": "2024-01-01T01:00:00Z",
                        },
                    ],
                    "next_cursor": None,
                },
            )
        )

        result = client.experiments.list_updates("exp-123")

        assert len(result.updates) == 2
        assert result.updates[0].id == "upd-001"
        assert result.updates[0].name == "Experiment created"
        assert result.next_cursor is None

    @respx.mock
    def test_list_updates_with_pagination(self, client: FoundryClient) -> None:
        """Should list updates with pagination params."""
        respx.get("https://api.test.com/experiments/exp-123/updates").mock(
            return_value=Response(
                200,
                json={
                    "updates": [],
                    "next_cursor": "cursor-123",
                },
            )
        )

        result = client.experiments.list_updates("exp-123", cursor="prev-cursor", limit=10)

        assert result.next_cursor == "cursor-123"


class TestTargetsAPI:
    """Test targets endpoint."""

    @respx.mock
    def test_get_target(self, client: FoundryClient) -> None:
        """Should get target by ID."""
        respx.get("https://api.test.com/targets/target-123").mock(
            return_value=Response(
                200,
                json={
                    "id": "target-123",
                    "name": "PD-L1",
                    "vendor_name": "ACROBiosystems",
                    "catalog_number": "PD1-H5220",
                },
            )
        )

        result = client.targets.get("target-123")

        assert result.id == "target-123"
        assert result.name == "PD-L1"

    @respx.mock
    def test_list_targets(self, client: FoundryClient) -> None:
        """Should list targets with pagination."""
        respx.get("https://api.test.com/targets").mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {
                            "id": "target-1",
                            "name": "PD-L1",
                            "vendor_name": "ACROBiosystems",
                            "catalog_number": "PD1-H5220",
                        }
                    ],
                    "total": 100,
                    "count": 1,
                    "offset": 0,
                },
            )
        )

        result = client.targets.list()

        assert len(result.targets) == 1
        assert result.targets[0].name == "PD-L1"
        assert result.total == 100

    @respx.mock
    def test_list_targets_selfservice_only(self, client: FoundryClient) -> None:
        """Should filter targets by selfservice_only."""
        route = respx.get("https://api.test.com/targets").mock(
            return_value=Response(
                200,
                json={
                    "targets": [],
                    "total": 0,
                    "count": 0,
                    "offset": 0,
                },
            )
        )

        client.targets.list(selfservice_only=True)

        assert route.calls[0].request.url.params["selfservice_only"] == "true"

    @respx.mock
    def test_search_targets_selfservice_only(self, client: FoundryClient) -> None:
        """Should filter search results by selfservice_only."""
        route = respx.get("https://api.test.com/targets").mock(
            return_value=Response(
                200,
                json={
                    "targets": [],
                    "total": 0,
                    "count": 0,
                    "offset": 0,
                },
            )
        )

        client.targets.search("PD-L1", selfservice_only=True)

        assert route.calls[0].request.url.params["search"] == "PD-L1"
        assert route.calls[0].request.url.params["selfservice_only"] == "true"


class TestUpdatesAPI:
    """Test global updates endpoint."""

    @respx.mock
    def test_list_updates(self, client: FoundryClient) -> None:
        """Should list global updates."""
        respx.get("https://api.test.com/updates").mock(
            return_value=Response(
                200,
                json={
                    "updates": [
                        {
                            "id": "upd-001",
                            "experiment_id": "exp-123",
                            "experiment_code": "EXP-001",
                            "name": "Status changed",
                            "timestamp": "2024-01-01T00:00:00Z",
                        }
                    ],
                    "next_cursor": "cursor-abc",
                },
            )
        )

        result = client.updates.list(limit=10)

        assert len(result.updates) == 1
        assert result.updates[0].id == "upd-001"
        assert result.next_cursor == "cursor-abc"

    @respx.mock
    def test_list_updates_with_filters(self, client: FoundryClient) -> None:
        """Should pass filter params to API."""
        route = respx.get("https://api.test.com/updates").mock(
            return_value=Response(200, json={"updates": [], "next_cursor": None})
        )

        client.updates.list(experiment_id="exp-123", cursor="cur-1", limit=20)

        assert route.calls[0].request.url.params["experiment_id"] == "exp-123"
        assert route.calls[0].request.url.params["cursor"] == "cur-1"
        assert route.calls[0].request.url.params["limit"] == "20"


class TestErrorHandling:
    """Test error handling."""

    @respx.mock
    def test_handles_401(self, client: FoundryClient) -> None:
        """Should raise AuthenticationError on 401."""
        respx.get("https://api.test.com/experiments/123").mock(
            return_value=Response(401, json={"error": "Invalid API key"})
        )

        with pytest.raises(AuthenticationError):
            client.experiments.get("123")

    @respx.mock
    def test_handles_404(self, client: FoundryClient) -> None:
        """Should raise NotFoundError on 404."""
        respx.get("https://api.test.com/experiments/123").mock(
            return_value=Response(404, json={"error": "Not found"})
        )

        with pytest.raises(NotFoundError):
            client.experiments.get("123")

    @respx.mock
    def test_handles_500(self, client: FoundryClient) -> None:
        """Should raise APIError on 500."""
        respx.get("https://api.test.com/experiments/123").mock(
            return_value=Response(500, json={"error": "Internal error"})
        )

        with pytest.raises(APIError) as exc_info:
            client.experiments.get("123")

        assert exc_info.value.status_code == 500

    @respx.mock
    def test_handles_429_rate_limit(self, client: FoundryClient) -> None:
        """Should raise RateLimitError on 429."""
        respx.get("https://api.test.com/experiments/123").mock(
            return_value=Response(
                429,
                json={"error": "Rate limit exceeded"},
                headers={"Retry-After": "5"},
            )
        )

        with pytest.raises(RateLimitError) as exc_info:
            client.experiments.get("123")

        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 5.0
        assert exc_info.value.retryable is True

    @respx.mock
    def test_api_error_includes_request_context(self, client: FoundryClient) -> None:
        """Should include request_id and request_path in APIError."""
        respx.get("https://api.test.com/experiments/123").mock(
            return_value=Response(
                500,
                json={"error": "Internal error"},
                headers={"X-Request-ID": "req-abc123"},
            )
        )

        with pytest.raises(APIError) as exc_info:
            client.experiments.get("123")

        assert exc_info.value.request_id == "req-abc123"
        assert exc_info.value.request_path == "/experiments/123"
        assert "req-abc123" in str(exc_info.value)

    @respx.mock
    def test_not_found_error_includes_context(self, client: FoundryClient) -> None:
        """Should include request context in NotFoundError."""
        respx.get("https://api.test.com/experiments/123").mock(
            return_value=Response(
                404,
                json={"error": "Not found"},
                headers={"X-Request-ID": "req-xyz"},
            )
        )

        with pytest.raises(NotFoundError) as exc_info:
            client.experiments.get("123")

        assert exc_info.value.request_id == "req-xyz"
        assert exc_info.value.request_path == "/experiments/123"

    @respx.mock
    def test_handles_403_permission_denied(self, client: FoundryClient) -> None:
        """Should raise PermissionDeniedError on 403."""
        respx.post("https://api.test.com/experiments").mock(
            return_value=Response(
                403,
                json={"error": "API key lacks create_experiment permission"},
                headers={"X-Request-ID": "req-403"},
            )
        )

        with pytest.raises(PermissionDeniedError) as exc_info:
            client.experiments.create(
                name="Test",
                experiment_spec={
                    "experiment_type": "thermostability",
                    "sequences": {"seq1": "MVKVGVNG"},
                },
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.request_id == "req-403"
        assert "create_experiment" in str(exc_info.value)


class TestRetryLogic:
    """Test exponential backoff retry logic."""

    @respx.mock
    def test_retries_on_500_error(self) -> None:
        """Should retry 500 errors with exponential backoff."""
        # Create client with minimal retry config for fast tests
        client = FoundryClient(
            api_key="test-key",
            base_url="https://api.test.com",
            retry_config=RetryConfig(max_attempts=2, backoff_factor=0.1, jitter=False),
        )

        # First request fails, second succeeds
        route = respx.get("https://api.test.com/experiments/123")
        route.side_effect = [
            Response(500, json={"error": "Internal error"}),
            Response(
                200,
                json={
                    "id": "123",
                    "name": "Test",
                    "code": "EXP-001",
                    "status": "waiting_for_confirmation",
                    "experiment_spec": {"experiment_type": "screening"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "results_status": "none",
                    "experiment_url": "https://app.example.com/exp/123",
                },
            ),
        ]

        result = client.experiments.get("123")
        assert result.id == "123"
        assert route.call_count == 2

    @respx.mock
    def test_does_not_retry_400_errors(self) -> None:
        """Should not retry 400 client errors."""
        client = FoundryClient(
            api_key="test-key",
            base_url="https://api.test.com",
            retry_config=RetryConfig(max_attempts=3),
        )

        route = respx.get("https://api.test.com/experiments/123").mock(
            return_value=Response(400, json={"error": "Bad request"})
        )

        with pytest.raises(ValidationError):
            client.experiments.get("123")

        # Should only be called once (no retries)
        assert route.call_count == 1

    @respx.mock
    def test_max_retries_exceeded(self) -> None:
        """Should raise after max retries exceeded."""
        client = FoundryClient(
            api_key="test-key",
            base_url="https://api.test.com",
            retry_config=RetryConfig(max_attempts=2, backoff_factor=0.01, jitter=False),
        )

        route = respx.get("https://api.test.com/experiments/123").mock(
            return_value=Response(500, json={"error": "Internal error"})
        )

        with pytest.raises(APIError):
            client.experiments.get("123")

        # Initial request + 2 retries = 3 calls
        assert route.call_count == 3


class TestContextManager:
    """Test context manager support."""

    def test_context_manager_closes_client(self) -> None:
        """Should close client on exit."""
        with FoundryClient(api_key="test-key", base_url="https://api.test.com") as client:
            assert client._client is not None

        # After exit, client should be closed
        assert client._client.is_closed


class TestRetryConfig:
    """Test RetryConfig backoff calculations."""

    def test_exponential_backoff(self) -> None:
        """Should calculate exponential backoff correctly."""
        config = RetryConfig(backoff_factor=2.0, max_backoff=30.0, jitter=False)

        assert config.get_backoff(0) == 1.0  # 2^0 = 1
        assert config.get_backoff(1) == 2.0  # 2^1 = 2
        assert config.get_backoff(2) == 4.0  # 2^2 = 4
        assert config.get_backoff(3) == 8.0  # 2^3 = 8

    def test_backoff_capped_at_max(self) -> None:
        """Should cap backoff at max_backoff."""
        config = RetryConfig(backoff_factor=2.0, max_backoff=5.0, jitter=False)

        assert config.get_backoff(10) == 5.0  # Would be 1024, capped at 5

    def test_backoff_with_jitter(self) -> None:
        """Should add jitter when enabled."""
        config = RetryConfig(backoff_factor=2.0, max_backoff=30.0, jitter=True)

        # Jitter adds 0-1 seconds
        backoff = config.get_backoff(0)
        assert 1.0 <= backoff <= 2.0


class TestSequencesAPI:
    """Test sequences endpoint."""

    @respx.mock
    def test_list_sequences(self, client: FoundryClient) -> None:
        """Should list sequences with pagination."""
        respx.get("https://api.test.com/sequences").mock(
            return_value=Response(
                200,
                json={
                    "sequences": [
                        {
                            "id": "seq-001",
                            "name": "Design A",
                            "fasta_preview": "MVKVGVNG",
                            "length": 8,
                            "is_control": False,
                            "experiment_id": "exp-123",
                            "experiment_code": "EXP-2024-001",
                            "created_at": "2024-01-01T00:00:00Z",
                        },
                        {
                            "id": "seq-002",
                            "name": "Control",
                            "fasta_preview": "MVKVGVNGAA",
                            "length": 10,
                            "is_control": True,
                            "experiment_id": "exp-123",
                            "experiment_code": "EXP-2024-001",
                            "created_at": "2024-01-01T00:00:00Z",
                        },
                    ],
                    "total": 2,
                    "count": 2,
                    "offset": 0,
                },
            )
        )

        result = client.sequences.list()

        assert len(result.sequences) == 2
        assert result.sequences[0].id == "seq-001"
        assert result.sequences[0].name == "Design A"
        assert result.sequences[1].is_control is True
        assert result.total == 2

    @respx.mock
    def test_list_sequences_with_filters(self, client: FoundryClient) -> None:
        """Should list sequences with experiment_id filter."""
        route = respx.get("https://api.test.com/sequences").mock(
            return_value=Response(
                200,
                json={
                    "sequences": [],
                    "total": 0,
                    "count": 0,
                    "offset": 0,
                },
            )
        )

        client.sequences.list(experiment_id="exp-123", search="design", limit=10, offset=5)

        # Verify query params were sent
        assert route.calls[0].request.url.params["experiment_id"] == "exp-123"
        assert route.calls[0].request.url.params["search"] == "design"
        assert route.calls[0].request.url.params["limit"] == "10"
        assert route.calls[0].request.url.params["offset"] == "5"

    @respx.mock
    def test_get_sequence(self, client: FoundryClient) -> None:
        """Should get sequence details."""
        respx.get("https://api.test.com/sequences/seq-001").mock(
            return_value=Response(
                200,
                json={
                    "id": "seq-001",
                    "aa_string": "MVKVGVNG",
                    "length": 8,
                    "name": "Design A",
                    "is_control": False,
                    "experiment": {
                        "experiment_id": "exp-123",
                        "experiment_code": "EXP-2024-001",
                        "experiment_status": "in_production",
                    },
                    "created_at": "2024-01-01T00:00:00Z",
                    "metadata": {"vh": "EVQLV..."},
                },
            )
        )

        result = client.sequences.get("seq-001")

        assert result.id == "seq-001"
        assert result.aa_string == "MVKVGVNG"
        assert result.length == 8
        assert result.experiment.experiment_id == "exp-123"
        assert result.experiment.experiment_status == "in_production"
        assert result.metadata is not None

    @respx.mock
    def test_create_sequences(self, client: FoundryClient) -> None:
        """Should append sequences to experiment."""
        respx.post("https://api.test.com/sequences").mock(
            return_value=Response(
                200,
                json={
                    "added_count": 2,
                    "experiment_id": "exp-123",
                    "experiment_code": "EXP-2024-001",
                    "sequence_ids": ["seq-001", "seq-002"],
                },
            )
        )

        result = client.sequences.create(
            experiment_code="EXP-2024-001",
            sequences=[
                {"aa_string": "MVKVGVNG", "name": "Design A"},
                {"aa_string": "MVKVGVNGAA", "name": "Design B", "control": True},
            ],
        )

        assert result.added_count == 2
        assert result.experiment_id == "exp-123"
        assert len(result.sequence_ids) == 2


class TestResultsAPI:
    """Test results endpoint."""

    @respx.mock
    def test_list_results(self, client: FoundryClient) -> None:
        """Should list results with pagination."""
        respx.get("https://api.test.com/results").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "id": "res-001",
                            "title": "Affinity Results Batch 1",
                            "experiment_id": "exp-123",
                            "result_type": "affinity",
                            "created_at": "2024-01-15T00:00:00Z",
                        },
                        {
                            "id": "res-002",
                            "title": "Thermostability Results",
                            "experiment_id": "exp-124",
                            "result_type": "thermostability",
                            "created_at": "2024-01-16T00:00:00Z",
                        },
                    ],
                    "total": 2,
                    "count": 2,
                    "offset": 0,
                },
            )
        )

        result = client.results.list()

        assert len(result.results) == 2
        assert result.results[0].id == "res-001"
        assert result.results[0].result_type == "affinity"
        assert result.results[1].result_type == "thermostability"
        assert result.total == 2

    @respx.mock
    def test_list_results_with_experiment_filter(self, client: FoundryClient) -> None:
        """Should filter results by experiment_id."""
        route = respx.get("https://api.test.com/results").mock(
            return_value=Response(
                200,
                json={
                    "results": [],
                    "total": 0,
                    "count": 0,
                    "offset": 0,
                },
            )
        )

        client.results.list(experiment_id="exp-123", limit=10, offset=5)

        assert route.calls[0].request.url.params["experiment_id"] == "exp-123"
        assert route.calls[0].request.url.params["limit"] == "10"
        assert route.calls[0].request.url.params["offset"] == "5"

    @respx.mock
    def test_get_result(self, client: FoundryClient) -> None:
        """Should get result details including kinetic parameters."""
        respx.get("https://api.test.com/results/res-001").mock(
            return_value=Response(
                200,
                json={
                    "id": "res-001",
                    "title": "Affinity Results Batch 1",
                    "experiment_id": "exp-123",
                    "result_type": "affinity",
                    "created_at": "2024-01-15T00:00:00Z",
                    "summary": [
                        {
                            "sequence_id": "seq-001",
                            "sequence_name": "Design A",
                            "target_id": "tgt-001",
                            "n_replicates": 3,
                            "kd": [1.2, 1.3, 1.1],
                            "kd_units": "nM",
                            "kon": 1.5e5,
                            "koff": 1.8e-4,
                            "binding_strength": "strong",
                        }
                    ],
                    "data_package_url": "https://storage.example.com/data.zip",
                    "metadata": {"author": "Lab Team", "version": "1.0"},
                },
            )
        )

        result = client.results.get("res-001")

        assert result.id == "res-001"
        assert result.title == "Affinity Results Batch 1"
        assert result.result_type == "affinity"
        assert result.data_package_url == "https://storage.example.com/data.zip"
        assert len(result.summary) == 1
        assert result.summary[0]["kd"] == [1.2, 1.3, 1.1]
        assert result.summary[0]["binding_strength"] == "strong"


class TestAutoconfirmPayload:
    """Test autoconfirm (skip_draft) payload handling."""

    @respx.mock
    def test_create_with_skip_draft_sends_correct_payload(self, client: FoundryClient) -> None:
        """confirmed=True should send skip_draft=True in API payload."""
        import json

        route = respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        client.experiments.create(
            name="Test",
            experiment_spec={
                "experiment_type": "thermostability",
                "sequences": {"s1": "MVKVGVNG"},
            },
            confirmed=True,
        )

        request_body = route.calls[0].request.content.decode()
        payload = json.loads(request_body)
        assert payload.get("skip_draft") is True
        assert "confirmed" not in payload  # Ensure old key not present

    @respx.mock
    def test_create_without_confirmed_no_skip_draft(self, client: FoundryClient) -> None:
        """confirmed=False (default) should NOT include skip_draft in payload."""
        route = respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        client.experiments.create(
            name="Test",
            experiment_spec={
                "experiment_type": "thermostability",
                "sequences": {"s1": "MVKVGVNG"},
            },
        )

        request_body = route.calls[0].request.content.decode()
        assert "skip_draft" not in request_body


class TestUpdatePriority:
    """Test update_priority endpoint."""

    @respx.mock
    def test_update_priority(self, client: FoundryClient) -> None:
        """Should update experiment priority."""
        import json

        route = respx.post("https://api.test.com/experiments/exp-123/update-priority").mock(
            return_value=Response(200, json={"success": True})
        )

        result = client.experiments.update_priority("exp-123", priority=5)

        assert result == {"success": True}
        request_body = route.calls[0].request.content.decode()
        assert json.loads(request_body) == {"priority": 5}


class TestExperimentsGetResults:
    """Test experiments.get_results() method."""

    @respx.mock
    def test_get_experiment_results(self, client: FoundryClient) -> None:
        """Should get results for a specific experiment."""
        respx.get("https://api.test.com/experiments/exp-123/results").mock(
            return_value=Response(
                200,
                json={
                    "results": [
                        {
                            "id": "res-001",
                            "title": "Affinity Results",
                            "experiment_id": "exp-123",
                            "result_type": "affinity",
                            "created_at": "2024-01-15T00:00:00Z",
                        }
                    ],
                    "total": 1,
                    "count": 1,
                    "offset": 0,
                },
            )
        )

        result = client.experiments.get_results("exp-123")

        assert len(result.results) == 1
        assert result.results[0].experiment_id == "exp-123"

    @respx.mock
    def test_get_experiment_results_with_pagination(self, client: FoundryClient) -> None:
        """Should pass pagination params to experiment results."""
        route = respx.get("https://api.test.com/experiments/exp-123/results").mock(
            return_value=Response(
                200,
                json={
                    "results": [],
                    "total": 0,
                    "count": 0,
                    "offset": 0,
                },
            )
        )

        client.experiments.get_results("exp-123", limit=10, offset=5)

        assert route.calls[0].request.url.params["limit"] == "10"
        assert route.calls[0].request.url.params["offset"] == "5"
