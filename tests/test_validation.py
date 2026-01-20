"""Tests for input validation."""

import pytest

from adaptyv.exceptions import ValidationError
from adaptyv.validation import (
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
