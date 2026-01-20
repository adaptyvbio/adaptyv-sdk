"""Tests for Supabase storage adapter."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from adaptyv.workflows.design_a_protein import DesignAProteinDesign

# Mock the supabase module before importing SupabaseStorage
mock_supabase = MagicMock()
sys.modules["supabase"] = mock_supabase


@pytest.fixture(autouse=True)
def _supabase_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "supabase", mock_supabase)


class TestSupabaseStorage:
    """Tests for SupabaseStorage class."""

    def test_init_requires_credentials(self):
        """Should raise error when credentials missing."""
        with patch.dict("os.environ", {}, clear=True):
            from adaptyv.storage.supabase import SupabaseStorage

            with pytest.raises(ValueError, match="Supabase URL and key required"):
                SupabaseStorage()

    def test_init_from_env_vars(self):
        """Should accept credentials from environment variables."""
        mock_client = MagicMock()
        mock_supabase.create_client.return_value = mock_client

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://test.supabase.co",
                "SUPABASE_SERVICE_KEY": "test-key",
            },
        ):
            from adaptyv.storage.supabase import SupabaseStorage

            storage = SupabaseStorage()

            mock_supabase.create_client.assert_called_with("https://test.supabase.co", "test-key")
            assert storage.url == "https://test.supabase.co"
            assert storage.key == "test-key"
            assert storage.schema == "public"

    def test_init_with_explicit_credentials(self):
        """Should accept explicit credentials."""
        mock_client = MagicMock()
        mock_supabase.create_client.return_value = mock_client

        from adaptyv.storage.supabase import SupabaseStorage

        storage = SupabaseStorage(
            url="https://explicit.supabase.co",
            key="explicit-key",
            schema="theo",
        )

        assert storage.url == "https://explicit.supabase.co"
        assert storage.key == "explicit-key"
        assert storage.schema == "theo"

    def test_save_designs_empty_list(self):
        """Should return empty list for empty designs."""
        mock_client = MagicMock()
        mock_supabase.create_client.return_value = mock_client

        from adaptyv.storage.supabase import SupabaseStorage

        storage = SupabaseStorage(
            url="https://test.supabase.co",
            key="test-key",
        )

        result = storage.save_designs([], design_run_id="run-123")
        assert result == []

    def test_save_designs_inserts_rows(self):
        """Should insert designs into design_run_sequences."""
        # Setup mock chain
        mock_execute = MagicMock()
        mock_execute.data = [
            {"id": "uuid-1"},
            {"id": "uuid-2"},
        ]

        mock_insert = MagicMock()
        mock_insert.execute.return_value = mock_execute

        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert

        mock_schema = MagicMock()
        mock_schema.table.return_value = mock_table

        mock_client = MagicMock()
        mock_client.schema.return_value = mock_schema

        mock_supabase.create_client.return_value = mock_client

        from adaptyv.storage.supabase import SupabaseStorage

        storage = SupabaseStorage(
            url="https://test.supabase.co",
            key="test-key",
        )

        designs = [
            DesignAProteinDesign(
                design_id="design-001",
                sequence="MVKVGVNG",
                structure_path="/vol/test/s1.pdb",
                metrics={"mpnn_score": 0.95, "shape_complementarity": 0.72},
            ),
            DesignAProteinDesign(
                design_id="design-002",
                sequence="ALKVTING",
                structure_path="/vol/test/s2.pdb",
                metrics={"mpnn_score": 0.88},
            ),
        ]

        result = storage.save_designs(designs, design_run_id="run-123")

        # Verify insert was called
        mock_client.schema.assert_called_with("public")
        mock_schema.table.assert_called_with("design_run_sequences")

        # Verify inserted rows
        insert_call = mock_table.insert.call_args[0][0]
        assert len(insert_call) == 2
        assert insert_call[0]["design_id"] == "design-001"
        assert insert_call[0]["sequence"] == "MVKVGVNG"
        assert insert_call[0]["design_run_id"] == "run-123"
        assert insert_call[0]["structure_url"] == "/vol/test/s1.pdb"

        # Verify returned IDs
        assert result == ["uuid-1", "uuid-2"]

    def test_save_designs_with_batch_name(self):
        """Should use batch name prefix for design IDs."""
        mock_execute = MagicMock()
        mock_execute.data = [{"id": "uuid-1"}]

        mock_insert = MagicMock()
        mock_insert.execute.return_value = mock_execute

        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert

        mock_schema = MagicMock()
        mock_schema.table.return_value = mock_table

        mock_client = MagicMock()
        mock_client.schema.return_value = mock_schema

        mock_supabase.create_client.return_value = mock_client

        from adaptyv.storage.supabase import SupabaseStorage

        storage = SupabaseStorage(
            url="https://test.supabase.co",
            key="test-key",
        )

        designs = [
            DesignAProteinDesign(
                design_id="design-001",
                sequence="MVKVGVNG",
                structure_path="/vol/test/s1.pdb",
            ),
        ]

        storage.save_designs(designs, design_run_id="run-123", batch_name="batch_2024")

        insert_call = mock_table.insert.call_args[0][0]
        assert insert_call[0]["design_id"] == "batch_2024_000"

    def test_get_approved_designs(self):
        """Should query designs with approved reviews."""
        mock_execute = MagicMock()
        mock_execute.data = [
            {"id": "uuid-1", "sequence": "MVKVGVNG", "result_reviews": {"has_passed": True}},
        ]

        mock_eq = MagicMock()
        mock_eq.execute.return_value = mock_execute

        mock_select = MagicMock()
        mock_select.eq.return_value = mock_eq

        mock_table = MagicMock()
        mock_table.select.return_value = mock_select

        mock_schema = MagicMock()
        mock_schema.table.return_value = mock_table

        mock_client = MagicMock()
        mock_client.schema.return_value = mock_schema

        mock_supabase.create_client.return_value = mock_client

        from adaptyv.storage.supabase import SupabaseStorage

        storage = SupabaseStorage(
            url="https://test.supabase.co",
            key="test-key",
        )

        result = storage.get_approved_designs()

        assert len(result) == 1
        assert result[0]["sequence"] == "MVKVGVNG"

    def test_export_sequences_for_foundry(self):
        """Should export approved sequences as dict."""
        mock_execute = MagicMock()
        mock_execute.data = [
            {"design_id": "design-001", "sequence": "MVKVGVNG"},
            {"design_id": "design-002", "sequence": "ALKVTING"},
        ]

        mock_eq = MagicMock()
        mock_eq.execute.return_value = mock_execute

        mock_select = MagicMock()
        mock_select.eq.return_value = mock_eq

        mock_table = MagicMock()
        mock_table.select.return_value = mock_select

        mock_schema = MagicMock()
        mock_schema.table.return_value = mock_table

        mock_client = MagicMock()
        mock_client.schema.return_value = mock_schema

        mock_supabase.create_client.return_value = mock_client

        from adaptyv.storage.supabase import SupabaseStorage

        storage = SupabaseStorage(
            url="https://test.supabase.co",
            key="test-key",
        )

        result = storage.export_sequences_for_foundry()

        assert result == {
            "design-001": "MVKVGVNG",
            "design-002": "ALKVTING",
        }
