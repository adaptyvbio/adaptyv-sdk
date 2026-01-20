"""Input validation for Adaptyv Lab SDK."""

from __future__ import annotations

import re

from adaptyv.exceptions import ValidationError

AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def validate_sequence(seq: str, name: str = "sequence") -> None:
    """Validate amino acid sequence."""
    if not seq:
        raise ValidationError(f"{name} cannot be empty")
    invalid = set(seq.upper()) - AMINO_ACIDS
    if invalid:
        raise ValidationError(f"{name} contains invalid characters: {invalid}")


def validate_sequences(seqs: dict[str, str] | list[str]) -> None:
    """Validate multiple sequences."""
    items = seqs.items() if isinstance(seqs, dict) else enumerate(seqs)
    for key, seq in items:
        validate_sequence(seq, f"sequence[{key}]")


def validate_uuid(value: str, name: str = "id") -> None:
    """Validate UUID format."""
    if not UUID_RE.match(value):
        raise ValidationError(f"{name} must be a valid UUID, got: {value}")


def validate_url(value: str, name: str = "url") -> None:
    """Validate URL format."""
    if not value.startswith(("http://", "https://")):
        raise ValidationError(f"{name} must be a valid URL, got: {value}")
