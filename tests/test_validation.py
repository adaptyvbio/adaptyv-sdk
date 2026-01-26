"""Tests for input validation."""

import pytest

from adaptyv.exceptions import ValidationError
from adaptyv.validation import (
    normalize_sequences,
    validate_sequence,
    validate_sequences,
    validate_url,
    validate_uuid,
)


class TestValidateSequence:
    def test_valid_sequence(self) -> None:
        validate_sequence("MVKVGVNG")  # Should not raise

    def test_empty_sequence(self) -> None:
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_sequence("")

    def test_invalid_characters(self) -> None:
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_sequence("MVKX123")

    def test_valid_multichain_sequence(self) -> None:
        """Multi-chain sequence with colon separator should pass."""
        validate_sequence("MVKVGVNG:MKTAYIAK")

    def test_empty_chain_fails(self) -> None:
        """Empty chain in multi-chain sequence should fail."""
        with pytest.raises(ValidationError, match="Empty chain"):
            validate_sequence("MVKVGVNG::MKTAYIAK")

    def test_multichain_invalid_chars(self) -> None:
        """Invalid chars in any chain should fail."""
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_sequence("MVKVGVNG:MKTX1234")


class TestValidateSequences:
    def test_valid_list(self) -> None:
        validate_sequences(["MVKVG", "MKVLA"])

    def test_valid_dict(self) -> None:
        validate_sequences({"seq1": "MVKVG", "seq2": "MKVLA"})

    def test_invalid_in_list(self) -> None:
        with pytest.raises(ValidationError, match="sequence\\[1\\]"):
            validate_sequences(["MVKVG", "INVALID123"])


class TestValidateUuid:
    def test_valid_uuid(self) -> None:
        validate_uuid("4e7659cd-2d6a-53b5-b3ee-93896a7589d6")

    def test_invalid_uuid(self) -> None:
        with pytest.raises(ValidationError, match="must be a valid UUID"):
            validate_uuid("not-a-uuid")


class TestValidateUrl:
    def test_valid_https(self) -> None:
        validate_url("https://example.com/webhook")

    def test_valid_http(self) -> None:
        validate_url("http://localhost:8000")

    def test_invalid_url(self) -> None:
        with pytest.raises(ValidationError, match="must be a valid URL"):
            validate_url("not-a-url")


class TestNormalizeSequences:
    def test_list_to_dict(self) -> None:
        """List should be converted to dict with design_N keys."""
        result = normalize_sequences(["MVKVG", "MKVLA"])
        assert result == {"design_0": "MVKVG", "design_1": "MKVLA"}

    def test_dict_passthrough(self) -> None:
        """Dict should be returned as-is."""
        input_dict = {"seq1": "MVKVG", "seq2": "MKVLA"}
        result = normalize_sequences(input_dict)
        assert result is input_dict

    def test_empty_list(self) -> None:
        """Empty list should return empty dict."""
        result = normalize_sequences([])
        assert result == {}
