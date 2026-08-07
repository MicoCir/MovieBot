"""Property-based tests for label derivation from latent specifications.

Feature: silver-dataset-generation, Properties 3, 4, 5

Tests that the label derivation engine correctly rejects inconsistent
specifications, produces deterministic labels, and preserves labels
across seed variations.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from silver_dataset.generation.label_derivation import (
    InconsistentSpecError,
    derive_labels,
)
from silver_dataset.models.latent_spec import LatentSpecification
from silver_dataset.tests.strategies import (
    inconsistent_latent_spec_strategy,
    latent_spec_strategy,
)


@pytest.mark.property
@given(spec=inconsistent_latent_spec_strategy())
@settings(max_examples=100)
def test_contradictory_spec_rejected(spec: LatentSpecification):
    """For any LatentSpecification with contradictory route/tool/action,
    derive_labels SHALL raise InconsistentSpecError.

    **Validates: Requirement 3.4**
    """
    with pytest.raises(InconsistentSpecError) as exc_info:
        derive_labels(spec)
    assert len(exc_info.value.violations) > 0


@pytest.mark.property
@given(spec=latent_spec_strategy())
@settings(max_examples=100)
def test_valid_spec_produces_labels(spec: LatentSpecification):
    """For any valid LatentSpecification, derive_labels SHALL succeed.

    **Validates: Requirement 3.4**
    """
    labels = derive_labels(spec)
    assert labels["expected_route"] == spec.route
    assert labels["expected_tool"] == spec.tool
    assert labels["expected_action"] == spec.action


# Feature: silver-dataset-generation, Property 4: Label derivation determinism
# **Validates: Requirement 3.2**
@pytest.mark.property
@given(spec=latent_spec_strategy())
@settings(max_examples=100)
def test_label_derivation_determinism(spec: LatentSpecification):
    """For any valid LatentSpecification, calling derive_labels multiple times
    SHALL always produce identical results, and those results SHALL match the
    route, tool, and action declared in the specification.

    **Validates: Requirement 3.2**
    """
    labels_1 = derive_labels(spec)
    labels_2 = derive_labels(spec)
    labels_3 = derive_labels(spec)

    # All calls produce identical results
    assert labels_1 == labels_2
    assert labels_2 == labels_3

    # Results match the specification
    assert labels_1["expected_route"] == spec.route
    assert labels_1["expected_tool"] == spec.tool
    assert labels_1["expected_action"] == spec.action


# Feature: silver-dataset-generation, Property 5: Variation preserves labels and seed identity
# **Validates: Requirements 3.3, 3.5**
@pytest.mark.property
@given(spec=latent_spec_strategy(), variation=st.sampled_from(["paraphrase", "typo", "translation", "code-switch"]))
@settings(max_examples=100)
def test_variation_preserves_labels_and_seed(spec: LatentSpecification, variation: str):
    """For any variation of a seed specification, the derived labels and
    seed_scenario_id SHALL be preserved unchanged."""
    # Create a variation: same route/tool/action but different spec_id and variation_type
    seed_id = spec.seed_scenario_id if spec.seed_scenario_id else spec.spec_id

    variation_spec = spec.model_copy(update={
        "spec_id": f"{spec.spec_id}_var_{variation}",
        "variation_type": variation,
        "seed_scenario_id": seed_id,
    })

    seed_labels = derive_labels(spec)
    variation_labels = derive_labels(variation_spec)

    # Core labels preserved
    assert seed_labels["expected_route"] == variation_labels["expected_route"]
    assert seed_labels["expected_tool"] == variation_labels["expected_tool"]
    assert seed_labels["expected_action"] == variation_labels["expected_action"]

    # Seed identity preserved
    assert variation_labels["seed_scenario_id"] == seed_id
