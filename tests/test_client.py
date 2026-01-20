"""Tests for FoundryClient."""

import pytest
import respx
from httpx import Response

from adaptyv.client.foundry import FoundryClient
from adaptyv.config import RetryConfig
from adaptyv.exceptions import APIError, AuthenticationError, NotFoundError, RateLimitError


@pytest.fixture
def client() -> FoundryClient:
    """Create test client."""
    return FoundryClient(api_key="test-api-key", base_url="https://api.test.com")


class TestFoundryClientInit:
    """Test client initialization."""

    def test_requires_api_key(self) -> None:
        """Should raise error without API key."""
        with pytest.raises(AuthenticationError):
            FoundryClient(api_key="")

    def test_accepts_api_key(self) -> None:
        """Should accept valid API key."""
        client = FoundryClient(api_key="test-key")
        assert client._client is not None  # Client was created

    def test_uses_default_base_url(self) -> None:
        """Should use production URL by default."""
        client = FoundryClient(api_key="test-key")
        assert "foundry-api-public.adaptyvbio.com" in client._base_url

    def test_accepts_custom_base_url(self) -> None:
        """Should accept custom base URL."""
        client = FoundryClient(api_key="test-key", base_url="https://custom.api.com")
        assert client._base_url == "https://custom.api.com"


class TestExperimentsAPI:
    """Test experiments endpoint."""

    @respx.mock
    def test_create_experiment(self, client: FoundryClient) -> None:
        """Should create experiment and return ID."""
        respx.post("https://api.test.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        result = client.experiments.create(
            name="Test Experiment",
            experiment_spec={
                "experiment_type": "screening",
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

        client.experiments.create(
            name="Test",
            experiment_spec={
                "experiment_type": "screening",
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
                    "experiment_url": "https://foundry.adaptyvbio.com/exp/123",
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
                },
            )
        )

        result = client.experiments.get_quote("exp-123")

        assert result.experiment_id == "exp-123"
        assert result.quote_id == "qt_abc123"
        assert result.amount_total == 9900
        assert result.currency == "usd"
        assert result.status == "open"

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
                    "page": 1,
                    "per_page": 50,
                },
            )
        )

        result = client.targets.list()

        assert len(result.targets) == 1
        assert result.targets[0].name == "PD-L1"
        assert result.total == 100


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
                    "experiment_url": "https://foundry.adaptyvbio.com/exp/123",
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

        from adaptyv.exceptions import ValidationError

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
        with FoundryClient(api_key="test-key") as client:
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
