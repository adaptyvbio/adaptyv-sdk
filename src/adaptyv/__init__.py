"""Adaptyv Lab SDK - Python client for Foundry API and design workflows."""

import importlib
from typing import Any

# Only import lightweight exceptions eagerly - these are always needed for error handling
from adaptyv.exceptions import (
    AdaptyvLabError,
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
    "InternalFoundryClient",
    "FoundrySettings",
    "RetryConfig",
    "ExperimentResult",
    "Target",
    "CostEstimate",
    # Failure tracking
    "FailureTracker",
    "FailureStats",
    "SequenceResult",
    "ResultStatus",
    # Results parsing
    "parse_data_package",
    # Workflows - BindCraft
    "BindCraftConfig",
    "BindCraftDesign",
    "BindCraftRun",
    "BindCraftWorkflow",
    # Workflows - Design-A-Protein
    "DesignAProteinConfig",
    "DesignAProteinDesign",
    "DesignAProteinRun",
    "DesignAProteinWorkflow",
    # Workflows - Germinal
    "GerminalAdvancedConfig",
    "GerminalConfig",
    "GerminalDesign",
    "GerminalRun",
    "GerminalWorkflow",
    # Exceptions
    "AdaptyvLabError",
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
    "InternalFoundryClient": ("adaptyv.client.foundry", "InternalFoundryClient"),
    "FoundrySettings": ("adaptyv.config", "FoundrySettings"),
    "RetryConfig": ("adaptyv.config", "RetryConfig"),
    "Lab": ("adaptyv.lab", "Lab"),
    # Types
    "CostEstimate": ("adaptyv.types.internal", "CostEstimate"),
    "ExperimentResult": ("adaptyv.types.internal", "ExperimentResult"),
    "ResultStatus": ("adaptyv.types.internal", "ResultStatus"),
    "Target": ("adaptyv.types.internal", "Target"),
    # Results
    "FailureStats": ("adaptyv.results.failures", "FailureStats"),
    "FailureTracker": ("adaptyv.results.failures", "FailureTracker"),
    "SequenceResult": ("adaptyv.results.failures", "SequenceResult"),
    "parse_data_package": ("adaptyv.results.parser", "parse_data_package"),
    # Workflows - BindCraft
    "BindCraftConfig": ("adaptyv.workflows.bindcraft", "BindCraftConfig"),
    "BindCraftDesign": ("adaptyv.workflows.bindcraft", "BindCraftDesign"),
    "BindCraftRun": ("adaptyv.workflows.bindcraft", "BindCraftRun"),
    "BindCraftWorkflow": ("adaptyv.workflows.bindcraft", "BindCraftWorkflow"),
    # Workflows - Design-A-Protein
    "DesignAProteinConfig": (
        "adaptyv.workflows.design_a_protein",
        "DesignAProteinConfig",
    ),
    "DesignAProteinDesign": (
        "adaptyv.workflows.design_a_protein",
        "DesignAProteinDesign",
    ),
    "DesignAProteinRun": ("adaptyv.workflows.design_a_protein", "DesignAProteinRun"),
    "DesignAProteinWorkflow": (
        "adaptyv.workflows.design_a_protein",
        "DesignAProteinWorkflow",
    ),
    # Workflows - Germinal
    "GerminalAdvancedConfig": ("adaptyv.workflows.germinal", "GerminalAdvancedConfig"),
    "GerminalConfig": ("adaptyv.workflows.germinal", "GerminalConfig"),
    "GerminalDesign": ("adaptyv.workflows.germinal", "GerminalDesign"),
    "GerminalRun": ("adaptyv.workflows.germinal", "GerminalRun"),
    "GerminalWorkflow": ("adaptyv.workflows.germinal", "GerminalWorkflow"),
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
