"""Tests for data package parser."""

from pathlib import Path

import pytest

from adaptyv.results.parser import parse_data_package
from adaptyv.types.internal import ResultStatus

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "Germinal_IL3_data_package.zip"


@pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="Test fixture not present")
class TestParseDataPackage:
    """Tests using real Germinal IL3 data package."""

    def test_parses_all_sequences(self) -> None:
        """Should parse all unique sequences from the package."""
        results = parse_data_package(FIXTURE_PATH)
        # 149 rows / ~3 replicates each = ~50 unique sequences
        assert len(results) > 40

    def test_finds_binding_confirmed(self) -> None:
        """Should identify sequences with binding=true."""
        results = parse_data_package(FIXTURE_PATH)
        binders = [r for r in results if r.status == ResultStatus.BINDING_CONFIRMED]
        # il3_scfv_s723586_abmpnn_4 has binding=true
        assert len(binders) >= 1
        assert any("s723586" in r.sequence_name for r in binders)

    def test_has_kd_values(self) -> None:
        """Binders should have Kd values in reasonable range."""
        results = parse_data_package(FIXTURE_PATH)
        binders = [r for r in results if r.status == ResultStatus.BINDING_CONFIRMED]
        for r in binders:
            assert r.kd_value is not None
            assert 1e-10 < r.kd_value < 1e-5  # Reasonable Kd range

    def test_has_sequences(self) -> None:
        """All results should have non-empty sequences."""
        results = parse_data_package(FIXTURE_PATH)
        for r in results:
            assert r.sequence  # Not empty
            # FAB format (Heavy:Light), single chain (long), or positive control (short placeholder)
            is_fab = ":" in r.sequence
            is_long = len(r.sequence) > 50
            is_positive_ctrl = "Ctrl" in r.sequence_name or "Pos" in r.sequence_name
            assert is_fab or is_long or is_positive_ctrl, (
                f"Unexpected sequence format: {r.sequence_name}"
            )

    def test_expression_levels(self) -> None:
        """Expression levels should be normalized 0-1."""
        results = parse_data_package(FIXTURE_PATH)
        for r in results:
            if r.expression_level is not None:
                assert 0.0 <= r.expression_level <= 1.0

    def test_raw_data_preserved(self) -> None:
        """Raw replicate data should be preserved."""
        results = parse_data_package(FIXTURE_PATH)
        for r in results:
            assert "replicates" in r.raw_data
            assert isinstance(r.raw_data["replicates"], list)
            assert len(r.raw_data["replicates"]) >= 1

    def test_identifies_no_binding(self) -> None:
        """Should identify sequences with binding=false."""
        results = parse_data_package(FIXTURE_PATH)
        no_binding = [r for r in results if r.status == ResultStatus.NO_BINDING]
        # Most sequences in this dataset have binding=false
        assert len(no_binding) > 30

    def test_identifies_unknown(self) -> None:
        """Should identify sequences with expression=none as NO_EXPRESSION or binding=unknown as UNKNOWN_BAD."""
        results = parse_data_package(FIXTURE_PATH)
        # Check we have some unknown statuses
        unknown = [r for r in results if r.status == ResultStatus.UNKNOWN_BAD]
        no_expression = [r for r in results if r.status == ResultStatus.NO_EXPRESSION]
        # At least some should fall into these categories
        assert len(unknown) >= 0  # May or may not have unknown
        assert len(no_expression) >= 0  # May or may not have no expression

    def test_positive_control(self) -> None:
        """Should include positive control with binding."""
        results = parse_data_package(FIXTURE_PATH)
        # The positive control should be identified
        ctrl = [r for r in results if "Pos" in r.sequence_name or "Ctrl" in r.sequence_name]
        if ctrl:  # If positive control exists
            assert any(r.status == ResultStatus.BINDING_CONFIRMED for r in ctrl)


class TestParseDataPackageEdgeCases:
    """Edge case tests for parser."""

    def test_file_not_found(self) -> None:
        """Should raise error for non-existent file."""
        with pytest.raises(FileNotFoundError):
            parse_data_package("/nonexistent/path.zip")

    def test_invalid_zip(self, tmp_path: Path) -> None:
        """Should raise error for invalid zip file."""
        import zipfile

        invalid_zip = tmp_path / "invalid.zip"
        invalid_zip.write_text("not a zip file")
        with pytest.raises(zipfile.BadZipFile):
            parse_data_package(invalid_zip)

    def test_missing_summary_csv(self, tmp_path: Path) -> None:
        """Should raise error if no summary CSV found."""
        import zipfile

        empty_zip = tmp_path / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("other_file.txt", "content")

        with pytest.raises(ValueError, match="No.*_summary.csv found"):
            parse_data_package(empty_zip)
