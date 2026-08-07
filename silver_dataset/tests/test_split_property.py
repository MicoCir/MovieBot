"""Property-based tests for split assignment family cohesion and distribution.

Feature: silver-dataset-generation, Property 6: Split family cohesion

Tests that the split assignment algorithm places all LatentSpecifications
sharing the same seed_scenario_id in the same split, and that the overall
distribution approximates 60% dev, 25% test, 15% holdout.
"""

from collections import Counter, defaultdict

import pytest
from hypothesis import given, settings

from silver_dataset.generation.latent_engine import assign_splits, expand_matrix
from silver_dataset.models.case import Split
from silver_dataset.tests.strategies import latent_spec_strategy
from hypothesis import strategies as st


# Feature: silver-dataset-generation, Property 6: Split family cohesion
# **Validates: Requirement 2.6**
@pytest.mark.property
@given(
    specs=st.lists(latent_spec_strategy(), min_size=2, max_size=20),
    seed=st.integers(min_value=1, max_value=10000),
)
@settings(max_examples=100)
def test_split_family_cohesion(specs, seed):
    """For any set of LatentSpecifications sharing the same seed_scenario_id,
    the split assignment SHALL place all of them in the same split.

    **Validates: Requirement 2.6**
    """
    assignments = assign_splits(specs, seed=seed)

    # Group by seed_scenario_id (fall back to spec_id when None)
    families: dict[str, list[str]] = defaultdict(list)
    for spec in specs:
        family_key = spec.seed_scenario_id if spec.seed_scenario_id else spec.spec_id
        families[family_key].append(spec.spec_id)

    # All specs in the same family must land in exactly one split
    for family_key, spec_ids in families.items():
        splits_for_family = {assignments[spec_id] for spec_id in spec_ids}
        assert len(splits_for_family) == 1, (
            f"Family '{family_key}' has specs in multiple splits: {splits_for_family}"
        )


# Feature: silver-dataset-generation, Property 6 (distribution part)
# **Validates: Requirement 2.6**
@pytest.mark.silver
def test_split_distribution_approximates_target():
    """With enough specs, the distribution approximates 60% dev, 25% test, 15% holdout.

    Uses the default coverage matrix to generate a realistic-sized spec list,
    then verifies the split distribution falls within acceptable tolerances
    (±20% per bucket, accounting for hash-based family-level assignment).

    **Validates: Requirement 2.6**
    """
    from silver_dataset.models.coverage import default_coverage_matrix

    specs = expand_matrix(default_coverage_matrix())
    assignments = assign_splits(specs, seed=42)

    split_counts = Counter(assignments.values())
    total = len(assignments)

    assert total > 0, "Expected at least one spec from the default coverage matrix"

    dev_rate = split_counts[Split.dev] / total
    test_rate = split_counts[Split.test] / total
    holdout_rate = split_counts[Split.holdout] / total

    # Approximate distribution — tolerance of ±20% due to hash-based family assignment
    assert 0.4 <= dev_rate <= 0.8, (
        f"Dev rate {dev_rate:.2f} is out of the expected [0.40, 0.80] range"
    )
    assert 0.1 <= test_rate <= 0.4, (
        f"Test rate {test_rate:.2f} is out of the expected [0.10, 0.40] range"
    )
    assert 0.05 <= holdout_rate <= 0.25, (
        f"Holdout rate {holdout_rate:.2f} is out of the expected [0.05, 0.25] range"
    )
