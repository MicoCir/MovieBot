"""Domain models for the Silver Dataset.

Contains Pydantic schemas and enums that define the structure of dataset cases,
latent specifications, coverage matrices, fixtures, metrics, and generation metadata.
"""

from silver_dataset.models.coverage import CoverageCell, CoverageMatrix, default_coverage_matrix
from silver_dataset.models.fixtures import FixtureRegistry
from silver_dataset.models.latent_spec import LatentSpecification

__all__ = [
    "CoverageCell",
    "CoverageMatrix",
    "FixtureRegistry",
    "LatentSpecification",
    "default_coverage_matrix",
]
