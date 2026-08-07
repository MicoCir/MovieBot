"""Latent engine for building LatentSpecifications and assigning splits.

Provides functions to expand coverage matrices into latent specifications
and assign deterministic, family-cohesive dataset splits.
"""

import hashlib
from collections import defaultdict

from silver_dataset.models.case import Split
from silver_dataset.models.coverage import CoverageMatrix
from silver_dataset.models.latent_spec import LatentSpecification


def expand_matrix(matrix: CoverageMatrix) -> list[LatentSpecification]:
    """Expand a coverage matrix into individual LatentSpecification instances.

    Each cell generates count_target × languages × difficulties × variations
    specifications.

    Args:
        matrix: The coverage matrix to expand.

    Returns:
        List of LatentSpecification instances covering all combinations.
    """
    specs: list[LatentSpecification] = []
    for cell in matrix.cells:
        for lang in cell.languages:
            for diff in cell.difficulties:
                # Seed ID is shared across all variations within this combination
                seed_id = (
                    f"{cell.suite.value}_{cell.scenario_family}"
                    f"_{cell.scenario_type}_{lang}_{diff.value}"
                )
                for variation in cell.variations:
                    for count_idx in range(cell.count_target):
                        spec_id = f"{seed_id}_{variation}_{count_idx}"
                        fixture_id = cell.fixture_ids[0] if cell.fixture_ids else None

                        specs.append(
                            LatentSpecification(
                                spec_id=spec_id,
                                suite=cell.suite,
                                scenario_family=cell.scenario_family,
                                scenario_type=cell.scenario_type,
                                route=cell.route,
                                tool=cell.tool,
                                action=cell.action,
                                language=lang,
                                response_language=lang,
                                difficulty=diff,
                                fixture_id=fixture_id,
                                variation_type=variation if variation != "original" else None,
                                seed_scenario_id=seed_id,
                                tags=cell.tags.copy(),
                            )
                        )
    return specs


def assign_splits(
    specs: list[LatentSpecification],
    seed: int = 42,
) -> dict[str, Split]:
    """Assign splits by hashing seed_scenario_id to maintain family cohesion.

    Algorithm:
    1. Group specs by seed_scenario_id (falls back to spec_id if None)
    2. Hash each seed_scenario_id with the global seed using SHA-256
    3. Map hash % 100 to split boundaries: [0,60) → dev, [60,85) → test, [85,100) → holdout
    4. All variations of a seed land in the same split

    Args:
        specs: List of latent specifications to assign splits for.
        seed: Global seed for deterministic hashing. Defaults to 42.

    Returns:
        Dictionary mapping spec_id → Split for all specs.
    """
    # Group specs by their family key (seed_scenario_id or spec_id as fallback)
    families: dict[str, list[str]] = defaultdict(list)
    for spec in specs:
        family_key = spec.seed_scenario_id if spec.seed_scenario_id is not None else spec.spec_id
        families[family_key].append(spec.spec_id)

    # Assign a split to each family using deterministic hashing
    assignments: dict[str, Split] = {}
    for family_key, spec_ids in families.items():
        # Compute SHA-256 hash for cross-platform determinism
        hash_input = f"{seed}:{family_key}".encode("utf-8")
        hash_digest = hashlib.sha256(hash_input).hexdigest()
        bucket = int(hash_digest, 16) % 100

        # Map bucket to split: [0,60) → dev, [60,85) → test, [85,100) → holdout
        if bucket < 60:
            split = Split.dev
        elif bucket < 85:
            split = Split.test
        else:
            split = Split.holdout

        # All specs in the same family get the same split
        for spec_id in spec_ids:
            assignments[spec_id] = split

    return assignments
