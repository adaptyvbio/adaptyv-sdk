"""Tests for Lab class."""

import pytest
import respx
from httpx import Response

from adaptyv import Lab
from adaptyv.exceptions import ValidationError

BASE_URL = "https://api.test.com"


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADAPTYV_API_KEY", "test-api-key")
    monkeypatch.setenv("ADAPTYV_API_URL", BASE_URL)


def make_experiment_response(
    experiment_id: str = "exp-123",
    name: str = "Test",
    experiment_url: str = "https://app.example.com/exp/123",
) -> dict:
    """Create a mock experiment response."""
    return {
        "id": experiment_id,
        "name": name,
        "code": "EXP-001",
        "status": "waiting_for_confirmation",
        "experiment_spec": {"experiment_type": "screening", "sequences": {}},
        "created_at": "2024-01-01T00:00:00Z",
        "results_status": "none",
        "experiment_url": experiment_url,
    }


class TestLabSetup:
    def test_setup_with_api_key(self) -> None:
        lab = Lab.setup(api_key="explicit-key", base_url="https://api.example.com")
        assert lab._config.api_key == "explicit-key"

    def test_setup_from_env(self, mock_env: None) -> None:
        lab = Lab.setup()
        assert lab._config.api_key == "test-api-key"

    def test_setup_without_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from adaptyv.exceptions import AuthenticationError

        monkeypatch.delenv("ADAPTYV_API_KEY", raising=False)
        with pytest.raises(AuthenticationError, match="ADAPTYV_API_KEY"):
            Lab.setup(base_url="https://api.example.com")


class TestExperimentDecorator:
    @respx.mock
    def test_decorator_creates_experiment(self, mock_env: None) -> None:
        respx.post(f"{BASE_URL}/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )
        respx.get(f"{BASE_URL}/experiments/exp-123").mock(
            return_value=Response(200, json=make_experiment_response())
        )

        lab = Lab.setup()

        @lab.experiment(target="550e8400-e29b-41d4-a716-446655440000")
        def design_binders() -> list[str]:
            return ["MVKVGVNG", "MKVLVAG"]

        result = design_binders()

        assert result.experiment_id == "exp-123"
        assert result.experiment_url == "https://app.example.com/exp/123"
        assert result.sequences_submitted == 2

    @respx.mock
    def test_decorator_validates_return_type(self, mock_env: None) -> None:
        lab = Lab.setup()

        @lab.experiment(target="test-target")
        def bad_design() -> str:
            return "single-string"  # Should be list

        with pytest.raises(ValidationError, match="list"):
            bad_design()

    @respx.mock
    def test_decorator_validates_empty_return(self, mock_env: None) -> None:
        lab = Lab.setup()

        @lab.experiment(target="test-target")
        def empty_design() -> list[str]:
            return []

        with pytest.raises(ValidationError, match="no sequences"):
            empty_design()


class TestCreateExperiment:
    @respx.mock
    def test_create_with_list(self, mock_env: None) -> None:
        respx.post(f"{BASE_URL}/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )
        respx.get(f"{BASE_URL}/experiments/exp-123").mock(
            return_value=Response(200, json=make_experiment_response())
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
        respx.post(f"{BASE_URL}/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )
        respx.get(f"{BASE_URL}/experiments/exp-123").mock(
            return_value=Response(200, json=make_experiment_response())
        )

        lab = Lab.setup()
        result = lab.create_experiment(
            name="Test",
            sequences={"my_design_1": "MVKVGVNG", "my_design_2": "MKVLVAG"},
        )

        assert result.sequences_submitted == 2


@pytest.fixture
def clear_client_cache() -> None:
    from adaptyv.client.foundry import _client_cache

    _client_cache.clear()


class TestLabContextManager:
    @respx.mock
    def test_context_manager_closes_client(self, mock_env: None, clear_client_cache: None) -> None:
        respx.post(f"{BASE_URL}/experiments").mock(
            return_value=Response(200, json={"experiment_id": "exp-123"})
        )
        respx.get(f"{BASE_URL}/experiments/exp-123").mock(
            return_value=Response(200, json=make_experiment_response())
        )

        with Lab.setup() as lab:
            result = lab.create_experiment(
                name="Test",
                sequences=["MVKVGVNG"],
            )
            assert result.experiment_id == "exp-123"

        assert lab._client._client.is_closed

    def test_close_method(self, mock_env: None, clear_client_cache: None) -> None:
        lab = Lab.setup()
        lab.close()


class TestLabSingleton:
    def test_singleton_is_default_lab(self) -> None:
        from adaptyv._singleton import DefaultLab
        from adaptyv._singleton import lab as singleton_lab

        assert isinstance(singleton_lab, DefaultLab)

    def test_singleton_has_methods(self, mock_env: None, clear_client_cache: None) -> None:
        from adaptyv._singleton import lab as singleton_lab

        singleton_lab._lab = None

        assert hasattr(singleton_lab, "experiment")
        assert hasattr(singleton_lab, "create_experiment")
        assert hasattr(singleton_lab, "get_experiment")
        assert hasattr(singleton_lab, "confirm_experiment")
        assert hasattr(singleton_lab, "list_targets")
        assert hasattr(singleton_lab, "list_all_targets")
        assert hasattr(singleton_lab, "search_targets")
        assert hasattr(singleton_lab, "configure")
        assert hasattr(singleton_lab, "client")

        singleton_lab._lab = None

    @respx.mock
    def test_singleton_configure(self, mock_env: None, clear_client_cache: None) -> None:
        from adaptyv._singleton import lab as singleton_lab

        singleton_lab._lab = None
        singleton_lab.configure(api_key="custom-key")

        assert singleton_lab._lab is not None
        assert singleton_lab._lab._config.api_key == "custom-key"

        singleton_lab._lab = None

    @respx.mock
    def test_singleton_lazy_init(self, mock_env: None, clear_client_cache: None) -> None:
        from adaptyv._singleton import lab as singleton_lab

        singleton_lab._lab = None

        respx.get(f"{BASE_URL}/targets").mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {"id": "t1", "name": "Target 1", "vendor_name": "V", "catalog_number": "C"}
                    ],
                    "total": 1,
                    "count": 1,
                    "offset": 0,
                },
            )
        )

        targets = singleton_lab.list_targets()

        assert singleton_lab._lab is not None
        assert len(targets) == 1

        singleton_lab._lab = None


class TestListAllTargets:
    @respx.mock
    def test_list_all_targets_single_page(self, mock_env: None, clear_client_cache: None) -> None:
        respx.get(f"{BASE_URL}/targets").mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {"id": "t1", "name": "Target 1", "vendor_name": "V", "catalog_number": "C1"},
                        {"id": "t2", "name": "Target 2", "vendor_name": "V", "catalog_number": "C2"},
                    ],
                    "total": 2,
                    "count": 2,
                    "offset": 0,
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
        respx.get(f"{BASE_URL}/targets", params={"limit": "2", "offset": "0"}).mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {"id": "t1", "name": "Target 1", "vendor_name": "V", "catalog_number": "C1"},
                        {"id": "t2", "name": "Target 2", "vendor_name": "V", "catalog_number": "C2"},
                    ],
                    "total": 3,
                    "count": 2,
                    "offset": 0,
                },
            )
        )
        respx.get(f"{BASE_URL}/targets", params={"limit": "2", "offset": "2"}).mock(
            return_value=Response(
                200,
                json={
                    "targets": [
                        {"id": "t3", "name": "Target 3", "vendor_name": "V", "catalog_number": "C3"},
                    ],
                    "total": 3,
                    "count": 1,
                    "offset": 2,
                },
            )
        )

        lab = Lab.setup()
        targets = list(lab.list_all_targets(limit=2))

        assert len(targets) == 3
        assert targets[0]["name"] == "Target 1"
        assert targets[1]["name"] == "Target 2"
        assert targets[2]["name"] == "Target 3"
