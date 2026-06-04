"""Adaptyv SDK - Python client for Foundry API."""

import importlib
from typing import Any

# Only import lightweight exceptions eagerly - these are always needed for error handling
from adaptyv.exceptions import (
    AdaptyvError,
    APIError,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ValidationError,
)

__all__ = [
    # Zero-config singleton (primary entry point)
    "lab",
    # Core classes
    "Lab",
    "FoundryClient",
    "FoundryClientProtocol",
    "get_client",
    "AdaptyvConfig",
    "RetryConfig",
    "FOUNDRY_SPEC_VERSION",
    # Resource APIs
    "ExperimentsAPI",
    "TargetsAPI",
    "UpdatesAPI",
    "SequencesAPI",
    "ResultsAPI",
    "QuotesAPI",
    "TokensAPI",
    "FeedbackAPI",
    "InfoAPI",
    # Types
    "ExperimentResult",
    "ExperimentStatus",
    "Target",
    # Exceptions
    "AdaptyvError",
    "AuthenticationError",
    "APIError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ValidationError",
]

# Lazy import mapping: name -> (module_path, attribute_name)
# These are only loaded when actually accessed
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Zero-config singleton (primary entry point)
    "lab": ("adaptyv._singleton", "lab"),
    # Core
    "FoundryClient": ("adaptyv.client.foundry", "FoundryClient"),
    "FoundryClientProtocol": ("adaptyv.client.foundry", "FoundryClientProtocol"),
    "get_client": ("adaptyv.client.foundry", "get_client"),
    "AdaptyvConfig": ("adaptyv.config", "AdaptyvConfig"),
    "RetryConfig": ("adaptyv.config", "RetryConfig"),
    "FOUNDRY_SPEC_VERSION": ("adaptyv.config", "FOUNDRY_SPEC_VERSION"),
    "Lab": ("adaptyv.lab", "Lab"),
    # Resource APIs
    "ExperimentsAPI": ("adaptyv.client.foundry", "ExperimentsAPI"),
    "TargetsAPI": ("adaptyv.client.foundry", "TargetsAPI"),
    "UpdatesAPI": ("adaptyv.client.foundry", "UpdatesAPI"),
    "SequencesAPI": ("adaptyv.client.foundry", "SequencesAPI"),
    "ResultsAPI": ("adaptyv.client.foundry", "ResultsAPI"),
    "QuotesAPI": ("adaptyv.client.foundry", "QuotesAPI"),
    "TokensAPI": ("adaptyv.client.foundry", "TokensAPI"),
    "FeedbackAPI": ("adaptyv.client.foundry", "FeedbackAPI"),
    "InfoAPI": ("adaptyv.client.foundry", "InfoAPI"),
    # Types
    "ExperimentResult": ("adaptyv.types.internal", "ExperimentResult"),
    "ExperimentStatus": ("adaptyv.types.internal", "ExperimentStatus"),
    "Target": ("adaptyv.types.internal", "Target"),
}

# Cache for lazy-loaded modules to avoid repeated imports
_LAZY_CACHE: dict[str, Any] = {}


def __getattr__(name: str) -> Any:
    """Lazy import for heavy dependencies - only load when accessed."""
    if name in _LAZY_CACHE:
        return _LAZY_CACHE[name]

    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        _LAZY_CACHE[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__version__ = "0.1.0"
