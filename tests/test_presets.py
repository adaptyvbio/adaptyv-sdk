"""Tests for workflow presets."""

import pytest

from adaptyv.workflows import (
    BindCraftConfig,
    DesignAProteinConfig,
    GerminalConfig,
)
from adaptyv.workflows.presets import (
    Preset,
    apply_preset,
    get_preset,
    list_presets,
)


class TestListPresets:
    """Tests for list_presets function."""

    def test_list_design_a_protein_presets(self) -> None:
        """List presets for design-a-protein."""
        presets = list_presets("design-a-protein")

        assert len(presets) == 3
        names = {p.name for p in presets}
        assert names == {"conservative", "balanced", "exploratory"}

    def test_list_bindcraft_presets(self) -> None:
        """List presets for bindcraft."""
        presets = list_presets("bindcraft")

        assert len(presets) == 3
        names = {p.name for p in presets}
        assert names == {"fast", "balanced", "thorough"}

    def test_list_germinal_presets(self) -> None:
        """List presets for germinal."""
        presets = list_presets("germinal")

        assert len(presets) == 3
        names = {p.name for p in presets}
        assert names == {"vhh_default", "vhh_humanized", "scfv_default"}

    def test_list_unknown_workflow_raises(self) -> None:
        """Unknown workflow type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown workflow type"):
            list_presets("unknown")  # type: ignore[arg-type]

    def test_preset_has_description(self) -> None:
        """Each preset has a non-empty description."""
        for workflow_type in ["design-a-protein", "bindcraft", "germinal"]:
            for preset in list_presets(workflow_type):  # type: ignore[arg-type]
                assert isinstance(preset.description, str)
                assert len(preset.description) > 0


class TestGetPreset:
    """Tests for get_preset function."""

    def test_get_existing_preset(self) -> None:
        """Get a specific preset by name."""
        preset = get_preset("design-a-protein", "exploratory")

        assert preset.name == "exploratory"
        assert preset.workflow_type == "design-a-protein"
        assert "num_samples" in preset.parameters
        assert preset.parameters["num_samples"] == 10

    def test_get_unknown_preset_raises(self) -> None:
        """Unknown preset name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown preset"):
            get_preset("design-a-protein", "nonexistent")

    def test_get_unknown_workflow_raises(self) -> None:
        """Unknown workflow type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown workflow type"):
            get_preset("unknown", "balanced")  # type: ignore[arg-type]


class TestApplyPreset:
    """Tests for apply_preset function."""

    def test_apply_design_a_protein_conservative(self) -> None:
        """Apply conservative preset to DesignAProteinConfig."""
        config = DesignAProteinConfig()
        result = apply_preset(config, "conservative")

        assert result.num_samples == 3
        assert result.temperature == 0.05
        assert result.chain_lengths == (60, 80)

    def test_apply_design_a_protein_balanced(self) -> None:
        """Apply balanced preset to DesignAProteinConfig."""
        config = DesignAProteinConfig()
        result = apply_preset(config, "balanced")

        assert result.num_samples == 5
        assert result.temperature == 0.1
        assert result.chain_lengths == (50, 100)

    def test_apply_design_a_protein_exploratory(self) -> None:
        """Apply exploratory preset to DesignAProteinConfig."""
        config = DesignAProteinConfig()
        result = apply_preset(config, "exploratory")

        assert result.num_samples == 10
        assert result.temperature == 0.2
        assert result.chain_lengths == (40, 120)

    def test_apply_bindcraft_fast(self) -> None:
        """Apply fast preset to BindCraftConfig."""
        config = BindCraftConfig()
        result = apply_preset(config, "fast")

        assert result.n_trajectories == 20
        assert result.binder_lengths == [80]

    def test_apply_bindcraft_balanced(self) -> None:
        """Apply balanced preset to BindCraftConfig."""
        config = BindCraftConfig()
        result = apply_preset(config, "balanced")

        assert result.n_trajectories == 50
        assert result.binder_lengths == [70, 80, 90]

    def test_apply_bindcraft_thorough(self) -> None:
        """Apply thorough preset to BindCraftConfig."""
        config = BindCraftConfig()
        result = apply_preset(config, "thorough")

        assert result.n_trajectories == 100
        assert result.binder_lengths == [60, 70, 80, 90, 100]

    def test_apply_germinal_vhh_default(self) -> None:
        """Apply vhh_default preset to GerminalConfig."""
        config = GerminalConfig()
        result = apply_preset(config, "vhh_default")

        assert result.binder_format == "vhh"
        assert result.design_mode == "both"

    def test_apply_germinal_vhh_humanized(self) -> None:
        """Apply vhh_humanized preset to GerminalConfig."""
        config = GerminalConfig()
        result = apply_preset(config, "vhh_humanized")

        assert result.binder_format == "vhh"
        assert result.design_mode == "iglm"

    def test_apply_germinal_scfv_default(self) -> None:
        """Apply scfv_default preset to GerminalConfig."""
        config = GerminalConfig()
        result = apply_preset(config, "scfv_default")

        assert result.binder_format == "scfv"
        assert result.design_mode == "both"

    def test_apply_preserves_other_config_values(self) -> None:
        """Preset only overrides its specific parameters."""
        config = DesignAProteinConfig(
            hotspots=["A50", "A123"],
            contig_map="A1-413",
        )
        result = apply_preset(config, "exploratory")

        # Preset values applied
        assert result.num_samples == 10
        assert result.temperature == 0.2

        # Original values preserved
        assert result.hotspots == ["A50", "A123"]
        assert result.contig_map == "A1-413"

    def test_apply_does_not_modify_original(self) -> None:
        """apply_preset returns new config, does not modify original."""
        original = DesignAProteinConfig(num_samples=1)
        result = apply_preset(original, "exploratory")

        assert original.num_samples == 1  # unchanged
        assert result.num_samples == 10  # new value
        assert original is not result

    def test_apply_unknown_preset_raises(self) -> None:
        """Unknown preset name raises ValueError."""
        config = DesignAProteinConfig()
        with pytest.raises(ValueError, match="Unknown preset"):
            apply_preset(config, "nonexistent")

    def test_apply_wrong_workflow_preset_raises(self) -> None:
        """Using preset from wrong workflow raises ValueError."""
        config = DesignAProteinConfig()
        with pytest.raises(ValueError, match="Unknown preset"):
            apply_preset(config, "fast")  # fast is for bindcraft

    def test_apply_unknown_config_type_raises(self) -> None:
        """Unknown config type raises TypeError."""
        with pytest.raises(TypeError, match="Unknown config type"):
            apply_preset("not a config", "balanced")  # type: ignore[arg-type]


class TestPresetDataclass:
    """Tests for Preset dataclass structure."""

    def test_preset_fields(self) -> None:
        """Preset has required fields."""
        preset = Preset(
            name="test",
            workflow_type="design-a-protein",
            description="Test preset",
            parameters={"num_samples": 5},
        )

        assert preset.name == "test"
        assert preset.workflow_type == "design-a-protein"
        assert preset.description == "Test preset"
        assert preset.parameters == {"num_samples": 5}

    def test_preset_parameters_default_empty(self) -> None:
        """Preset parameters default to empty dict."""
        preset = Preset(
            name="test",
            workflow_type="design-a-protein",
            description="Test preset",
        )

        assert preset.parameters == {}


class TestPresetParameterValues:
    """Verify preset parameter values match specification."""

    def test_design_a_protein_conservative_values(self) -> None:
        """Conservative preset has correct values."""
        preset = get_preset("design-a-protein", "conservative")
        assert preset.parameters == {
            "num_samples": 3,
            "temperature": 0.05,
            "chain_lengths": (60, 80),
        }

    def test_design_a_protein_balanced_values(self) -> None:
        """Balanced preset has correct values."""
        preset = get_preset("design-a-protein", "balanced")
        assert preset.parameters == {
            "num_samples": 5,
            "temperature": 0.1,
            "chain_lengths": (50, 100),
        }

    def test_design_a_protein_exploratory_values(self) -> None:
        """Exploratory preset has correct values."""
        preset = get_preset("design-a-protein", "exploratory")
        assert preset.parameters == {
            "num_samples": 10,
            "temperature": 0.2,
            "chain_lengths": (40, 120),
        }

    def test_bindcraft_fast_values(self) -> None:
        """Fast preset has correct values."""
        preset = get_preset("bindcraft", "fast")
        assert preset.parameters == {
            "n_trajectories": 20,
            "binder_lengths": [80],
        }

    def test_bindcraft_balanced_values(self) -> None:
        """Balanced preset has correct values."""
        preset = get_preset("bindcraft", "balanced")
        assert preset.parameters == {
            "n_trajectories": 50,
            "binder_lengths": [70, 80, 90],
        }

    def test_bindcraft_thorough_values(self) -> None:
        """Thorough preset has correct values."""
        preset = get_preset("bindcraft", "thorough")
        assert preset.parameters == {
            "n_trajectories": 100,
            "binder_lengths": [60, 70, 80, 90, 100],
        }

    def test_germinal_vhh_default_values(self) -> None:
        """VHH default preset has correct values."""
        preset = get_preset("germinal", "vhh_default")
        assert preset.parameters == {
            "binder_format": "vhh",
            "design_mode": "both",
        }

    def test_germinal_vhh_humanized_values(self) -> None:
        """VHH humanized preset has correct values."""
        preset = get_preset("germinal", "vhh_humanized")
        assert preset.parameters == {
            "binder_format": "vhh",
            "design_mode": "iglm",
        }

    def test_germinal_scfv_default_values(self) -> None:
        """scFv default preset has correct values."""
        preset = get_preset("germinal", "scfv_default")
        assert preset.parameters == {
            "binder_format": "scfv",
            "design_mode": "both",
        }
