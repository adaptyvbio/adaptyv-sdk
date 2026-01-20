"""Tests for Lab class."""

import pytest
import respx
from httpx import Response

from adaptyv import Lab
from adaptyv.exceptions import ValidationError


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up test environment variables."""
    monkeypatch.setenv("ADAPTYV_API_KEY", "test-api-key")


class TestLabSetup:
    """Test Lab.setup()."""

    def test_setup_with_api_key(self) -> None:
        """Should accept explicit API key."""
        lab = Lab.setup(api_key="explicit-key")
        assert lab._settings.api_key == "explicit-key"

    def test_setup_from_env(self, mock_env: None) -> None:
        """Should read API key from environment."""
        lab = Lab.setup()
        assert lab._settings.api_key == "test-api-key"

    def test_setup_without_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise if no API key available."""
        monkeypatch.delenv("ADAPTYV_API_KEY", raising=False)
        with pytest.raises(ValueError, match="ADAPTYV_API_KEY"):
            Lab.setup()


class TestExperimentDecorator:
    """Test @lab.experiment decorator."""

    @respx.mock
    def test_decorator_creates_experiment(self, mock_env: None) -> None:
        """Should create experiment from decorated function."""
        # Mock create endpoint
        respx.post("https://foundry-api-public.adaptyvbio.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )

        # Mock get endpoint
        respx.get("https://foundry-api-public.adaptyvbio.com/experiments/exp-123").mock(
            return_value=Response(
                200,
                json={
                    "id": "exp-123",
                    "name": "Test",
                    "code": "EXP-001",
                    "status": "waiting_for_confirmation",
                    "experiment_spec": {
                        "experiment_type": "screening",
                        "sequences": {},
                    },
                    "created_at": "2024-01-01T00:00:00Z",
                    "results_status": "none",
                    "experiment_url": "https://foundry.adaptyvbio.com/exp/123",
                },
            )
        )

        lab = Lab.setup()

        @lab.experiment(target="550e8400-e29b-41d4-a716-446655440000", workflow="bindcraft")
        def design_binders() -> list[str]:
            return ["MVKVGVNG", "MKVLVAG"]

        result = design_binders()

        assert result.experiment_id == "exp-123"
        assert result.experiment_url == "https://foundry.adaptyvbio.com/exp/123"
        assert result.sequences_submitted == 2

    @respx.mock
    def test_decorator_validates_return_type(self, mock_env: None) -> None:
        """Should raise if function returns wrong type."""
        lab = Lab.setup()

        @lab.experiment(target="test-target", workflow="bindcraft")
        def bad_design() -> str:
            return "single-string"  # Should be list

        with pytest.raises(ValidationError, match="list"):
            bad_design()

    @respx.mock
    def test_decorator_validates_empty_return(self, mock_env: None) -> None:
        """Should raise if function returns empty list."""
        lab = Lab.setup()

        @lab.experiment(target="test-target", workflow="bindcraft")
        def empty_design() -> list[str]:
            return []

        with pytest.raises(ValidationError, match="no sequences"):
            empty_design()


class TestCreateExperiment:
    """Test Lab.create_experiment()."""

    @respx.mock
    def test_create_with_list(self, mock_env: None) -> None:
        """Should accept list of sequences."""
        respx.post("https://foundry-api-public.adaptyvbio.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )
        respx.get("https://foundry-api-public.adaptyvbio.com/experiments/exp-123").mock(
            return_value=Response(
                200,
                json={
                    "id": "exp-123",
                    "name": "Test",
                    "code": "EXP-001",
                    "status": "waiting_for_confirmation",
                    "experiment_spec": {"experiment_type": "screening", "sequences": {}},
                    "created_at": "2024-01-01T00:00:00Z",
                    "results_status": "none",
                    "experiment_url": "https://example.com",
                },
            )
        )

        lab = Lab.setup()
        result = lab.create_experiment(
            name="Test",
            sequences=["MVKVGVNG", "MKVLVAG"],
        )

        assert result.experiment_id == "exp-123"
        assert result.sequences_submitted == 2

    @respx.mock
    def test_create_with_dict(self, mock_env: None) -> None:
        """Should accept dict mapping names to sequences."""
        respx.post("https://foundry-api-public.adaptyvbio.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )
        respx.get("https://foundry-api-public.adaptyvbio.com/experiments/exp-123").mock(
            return_value=Response(
                200,
                json={
                    "id": "exp-123",
                    "name": "Test",
                    "code": "EXP-001",
                    "status": "waiting_for_confirmation",
                    "experiment_spec": {"experiment_type": "screening", "sequences": {}},
                    "created_at": "2024-01-01T00:00:00Z",
                    "results_status": "none",
                    "experiment_url": "https://example.com",
                },
            )
        )

        lab = Lab.setup()
        result = lab.create_experiment(
            name="Test",
            sequences={"my_design_1": "MVKVGVNG", "my_design_2": "MKVLVAG"},
        )

        assert result.sequences_submitted == 2


@pytest.fixture
def clear_client_cache() -> None:
    """Clear the client cache before each test."""
    from adaptyv.client.foundry import _client_cache

    _client_cache.clear()


class TestLabContextManager:
    """Test Lab context manager support."""

    @respx.mock
    def test_context_manager_closes_client(self, mock_env: None, clear_client_cache: None) -> None:
        """Should close client when exiting context."""
        respx.post("https://foundry-api-public.adaptyvbio.com/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )
        respx.get("https://foundry-api-public.adaptyvbio.com/experiments/exp-123").mock(
            return_value=Response(
                200,
                json={
                    "id": "exp-123",
                    "name": "Test",
                    "code": "EXP-001",
                    "status": "waiting_for_confirmation",
                    "experiment_spec": {"experiment_type": "screening", "sequences": {}},
                    "created_at": "2024-01-01T00:00:00Z",
                    "results_status": "none",
                    "experiment_url": "https://example.com",
                },
            )
        )

        with Lab.setup() as lab:
            result = lab.create_experiment(
                name="Test",
                sequences=["MVKVGVNG"],
            )
            assert result.experiment_id == "exp-123"

        # Client should be closed after context exit
        assert lab._client._client.is_closed

    def test_close_method(self, mock_env: None, clear_client_cache: None) -> None:
        """Should have a close() method."""
        lab = Lab.setup()
        # Should not raise
        lab.close()


class TestLabSingleton:
    """Test singleton lab module."""

    def test_singleton_is_default_lab(self) -> None:
        """Singleton should be a DefaultLab instance."""
        from adaptyv._singleton import DefaultLab
        from adaptyv._singleton import lab as singleton_lab

        assert isinstance(singleton_lab, DefaultLab)

    def test_singleton_has_methods(self) -> None:
        """Singleton should expose Lab methods."""
        from adaptyv._singleton import lab as singleton_lab

        # Check that key methods exist
        assert hasattr(singleton_lab, "experiment")
        assert hasattr(singleton_lab, "create_experiment")
        assert hasattr(singleton_lab, "get_experiment")
        assert hasattr(singleton_lab, "confirm_experiment")
        assert hasattr(singleton_lab, "list_targets")
        assert hasattr(singleton_lab, "list_all_targets")
        assert hasattr(singleton_lab, "search_targets")
        assert hasattr(singleton_lab, "configure")
        assert hasattr(singleton_lab, "client")

    @respx.mock
    def test_singleton_configure(self, mock_env: None, clear_client_cache: None) -> None:
        """Should allow configuration via configure()."""
        from adaptyv._singleton import lab as singleton_lab

        # Reset singleton state
        singleton_lab._lab = None

        # Configure with explicit key
        singleton_lab.configure(api_key="custom-key")

        # Should have configured underlying lab
        assert singleton_lab._lab is not None
        assert singleton_lab._lab._settings.api_key == "custom-key"

        # Reset for other tests
        singleton_lab._lab = None

    @respx.mock
    def test_singleton_lazy_init(self, mock_env: None, clear_client_cache: None) -> None:
        """Should initialize on first use."""
        from adaptyv._singleton import lab as singleton_lab

        # Reset singleton state
        singleton_lab._lab = None

        # Mock the API call
        respx.get("https://foundry-api-public.adaptyvbio.com/targets").mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {"id": "t1", "name": "Target 1", "vendor_name": "V", "catalog_number": "C"}
                    ],
                    "total": 1,
                    "page": 1,
                    "per_page": 50,
                },
            )
        )

        # Use the singleton
        targets = singleton_lab.list_targets()

        # Now lab should be initialized
        assert singleton_lab._lab is not None
        assert len(targets) == 1

        # Reset for other tests
        singleton_lab._lab = None


class TestListAllTargets:
    """Test pagination helper."""

    @respx.mock
    def test_list_all_targets_single_page(self, mock_env: None, clear_client_cache: None) -> None:
        """Should return all targets from single page."""
        respx.get("https://foundry-api-public.adaptyvbio.com/targets").mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {
                            "id": "t1",
                            "name": "Target 1",
                            "vendor_name": "V",
                            "catalog_number": "C1",
                        },
                        {
                            "id": "t2",
                            "name": "Target 2",
                            "vendor_name": "V",
                            "catalog_number": "C2",
                        },
                    ],
                    "total": 2,
                    "page": 1,
                    "per_page": 50,
                },
            )
        )

        lab = Lab.setup()
        targets = list(lab.list_all_targets())

        assert len(targets) == 2
        assert targets[0]["name"] == "Target 1"
        assert targets[1]["name"] == "Target 2"

    @respx.mock
    def test_list_all_targets_multiple_pages(
        self, mock_env: None, clear_client_cache: None
    ) -> None:
        """Should paginate through all pages."""
        # First page returns full results
        respx.get(
            "https://foundry-api-public.adaptyvbio.com/targets", params={"page": 1, "per_page": 2}
        ).mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {
                            "id": "t1",
                            "name": "Target 1",
                            "vendor_name": "V",
                            "catalog_number": "C1",
                        },
                        {
                            "id": "t2",
                            "name": "Target 2",
                            "vendor_name": "V",
                            "catalog_number": "C2",
                        },
                    ],
                    "total": 3,
                    "page": 1,
                    "per_page": 2,
                },
            )
        )

        # Second page returns partial results (indicating end)
        respx.get(
            "https://foundry-api-public.adaptyvbio.com/targets", params={"page": 2, "per_page": 2}
        ).mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {
                            "id": "t3",
                            "name": "Target 3",
                            "vendor_name": "V",
                            "catalog_number": "C3",
                        },
                    ],
                    "total": 3,
                    "page": 2,
                    "per_page": 2,
                },
            )
        )

        lab = Lab.setup()
        targets = list(lab.list_all_targets(per_page=2))

        assert len(targets) == 3
        assert targets[0]["name"] == "Target 1"
        assert targets[1]["name"] == "Target 2"
        assert targets[2]["name"] == "Target 3"
