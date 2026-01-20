"""Workflow presets for common design configurations.

Presets provide opinionated defaults for different design strategies:
- Conservative: Fewer samples, lower temperature, tighter constraints
- Balanced: Good defaults for most use cases
- Exploratory: More samples, higher temperature, wider search

Usage:
    from adaptyv.workflows.presets import list_presets, apply_preset
    from adaptyv.workflows import DesignAProteinConfig

    # List available presets
    presets = list_presets("design-a-protein")

    # Apply a preset to configuration
    config = DesignAProteinConfig()
    config = apply_preset(config, "exploratory")
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypeVar

from adaptyv.workflows.bindcraft import BindCraftConfig
from adaptyv.workflows.design_a_protein import DesignAProteinConfig
from adaptyv.workflows.germinal import GerminalConfig

WorkflowType = Literal["design-a-protein", "bindcraft", "germinal"]
WorkflowConfig = DesignAProteinConfig | BindCraftConfig | GerminalConfig
T = TypeVar("T", DesignAProteinConfig, BindCraftConfig, GerminalConfig)


@dataclass
class Preset:
    """A named configuration preset for a workflow.

    Attributes:
        name: Preset identifier (e.g., "conservative", "balanced", "exploratory")
        workflow_type: Which workflow this preset applies to
        description: Human-readable description of when to use this preset
        parameters: Dictionary of parameter overrides to apply
    """

    name: str
    workflow_type: WorkflowType
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Design-A-Protein Presets
# =============================================================================

DESIGN_A_PROTEIN_PRESETS: dict[str, Preset] = {
    "conservative": Preset(
        name="conservative",
        workflow_type="design-a-protein",
        description="Fewer samples with lower temperature for reliable, conservative designs. "
        "Best for well-characterized targets where you want high-confidence predictions.",
        parameters={
            "num_samples": 3,
            "temperature": 0.05,
            "chain_lengths": (60, 80),
        },
    ),
    "balanced": Preset(
        name="balanced",
        workflow_type="design-a-protein",
        description="Good defaults for most use cases. "
        "Moderate sample count and temperature for balanced exploration vs. quality.",
        parameters={
            "num_samples": 5,
            "temperature": 0.1,
            "chain_lengths": (50, 100),
        },
    ),
    "exploratory": Preset(
        name="exploratory",
        workflow_type="design-a-protein",
        description="More samples with higher temperature for diverse exploration. "
        "Best for novel targets or when you want to explore sequence space broadly.",
        parameters={
            "num_samples": 10,
            "temperature": 0.2,
            "chain_lengths": (40, 120),
        },
    ),
}


# =============================================================================
# BindCraft Presets
# =============================================================================

BINDCRAFT_PRESETS: dict[str, Preset] = {
    "fast": Preset(
        name="fast",
        workflow_type="bindcraft",
        description="Quick screening with fewer trajectories. "
        "Good for initial exploration or when compute budget is limited.",
        parameters={
            "n_trajectories": 20,
            "binder_lengths": [80],
        },
    ),
    "balanced": Preset(
        name="balanced",
        workflow_type="bindcraft",
        description="Good defaults for most use cases. "
        "Multiple binder lengths for better coverage of design space.",
        parameters={
            "n_trajectories": 50,
            "binder_lengths": [70, 80, 90],
        },
    ),
    "thorough": Preset(
        name="thorough",
        workflow_type="bindcraft",
        description="Deep exploration with many trajectories and binder lengths. "
        "Best for critical targets where you want highest quality designs.",
        parameters={
            "n_trajectories": 100,
            "binder_lengths": [60, 70, 80, 90, 100],
        },
    ),
}


# =============================================================================
# Germinal Presets
# =============================================================================

GERMINAL_PRESETS: dict[str, Preset] = {
    "vhh_default": Preset(
        name="vhh_default",
        workflow_type="germinal",
        description="Standard VHH (nanobody) design using both template and IgLM methods. "
        "Good starting point for nanobody binder design.",
        parameters={
            "binder_format": "vhh",
            "design_mode": "both",
        },
    ),
    "vhh_humanized": Preset(
        name="vhh_humanized",
        workflow_type="germinal",
        description="VHH design using IgLM only for better humanization. "
        "Prioritizes human-like sequences for therapeutic applications.",
        parameters={
            "binder_format": "vhh",
            "design_mode": "iglm",
        },
    ),
    "scfv_default": Preset(
        name="scfv_default",
        workflow_type="germinal",
        description="Standard scFv (single-chain Fv) design using both methods. "
        "For traditional antibody fragment designs with VH-VL linkage.",
        parameters={
            "binder_format": "scfv",
            "design_mode": "both",
        },
    ),
}


# =============================================================================
# Public API
# =============================================================================


def _get_presets_for_workflow(workflow_type: WorkflowType) -> dict[str, Preset]:
    """Get preset dict for a workflow type."""
    if workflow_type == "design-a-protein":
        return DESIGN_A_PROTEIN_PRESETS
    elif workflow_type == "bindcraft":
        return BINDCRAFT_PRESETS
    elif workflow_type == "germinal":
        return GERMINAL_PRESETS
    else:
        raise ValueError(
            f"Unknown workflow type: {workflow_type}. "
            "Valid types: design-a-protein, bindcraft, germinal"
        )


def list_presets(workflow_type: WorkflowType) -> list[Preset]:
    """List available presets for a workflow type.

    Args:
        workflow_type: One of "design-a-protein", "bindcraft", or "germinal"

    Returns:
        List of Preset objects available for the workflow

    Raises:
        ValueError: If workflow_type is not recognized

    Example:
        >>> presets = list_presets("design-a-protein")
        >>> for p in presets:
        ...     print(f"{p.name}: {p.description}")
    """
    return list(_get_presets_for_workflow(workflow_type).values())


def get_preset(workflow_type: WorkflowType, preset_name: str) -> Preset:
    """Get a specific preset by name.

    Args:
        workflow_type: One of "design-a-protein", "bindcraft", or "germinal"
        preset_name: Name of the preset (e.g., "balanced", "exploratory")

    Returns:
        The Preset object

    Raises:
        ValueError: If workflow_type or preset_name is not recognized
    """
    presets = _get_presets_for_workflow(workflow_type)
    if preset_name not in presets:
        valid_presets = ", ".join(presets.keys())
        raise ValueError(
            f"Unknown preset '{preset_name}' for {workflow_type}. Valid presets: {valid_presets}"
        )

    return presets[preset_name]


def apply_preset(config: T, preset_name: str) -> T:
    """Apply a preset to a workflow configuration.

    Creates a new configuration with preset parameters applied.
    The original config is not modified.

    Args:
        config: A workflow configuration object (DesignAProteinConfig, BindCraftConfig, or GerminalConfig)
        preset_name: Name of the preset to apply

    Returns:
        New configuration with preset parameters applied

    Raises:
        ValueError: If preset_name is not valid for the config type
        TypeError: If config is not a recognized workflow configuration

    Example:
        >>> from adaptyv.workflows import DesignAProteinConfig
        >>> config = DesignAProteinConfig(hotspots=["A50"])
        >>> config = apply_preset(config, "exploratory")
        >>> config.num_samples
        10
        >>> config.hotspots  # preserved from original
        ['A50']
    """
    # Determine workflow type from config
    if isinstance(config, DesignAProteinConfig):
        workflow_type: WorkflowType = "design-a-protein"
    elif isinstance(config, BindCraftConfig):
        workflow_type = "bindcraft"
    elif isinstance(config, GerminalConfig):
        workflow_type = "germinal"
    else:
        raise TypeError(
            f"Unknown config type: {type(config).__name__}. "
            "Expected DesignAProteinConfig, BindCraftConfig, or GerminalConfig."
        )

    preset = get_preset(workflow_type, preset_name)

    # Create a new config with preset parameters merged
    # Start with current config values, then override with preset
    config_dict = asdict(config)
    config_dict.update(preset.parameters)

    # Reconstruct the config (filter to valid fields only)
    valid_fields = set(type(config).__dataclass_fields__.keys())
    filtered = {k: v for k, v in config_dict.items() if k in valid_fields}
    return type(config)(**filtered)
