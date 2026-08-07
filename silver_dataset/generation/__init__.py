"""Query generation pipeline.

Handles latent spec expansion, deterministic label derivation, Ollama-based
natural language query generation, variation engines, and checkpoint management.
"""

from silver_dataset.generation.checkpoint import CheckpointManager
from silver_dataset.generation.label_derivation import (
    InconsistentSpecError,
    derive_labels,
    validate_spec_consistency,
)
from silver_dataset.generation.latent_engine import assign_splits, expand_matrix
from silver_dataset.generation.query_generator import (
    OllamaQueryGenerator,
    OllamaUnavailableError,
    RetryConfig,
)
from silver_dataset.generation.variation_engine import VariationEngine

__all__ = [
    "CheckpointManager",
    "InconsistentSpecError",
    "OllamaQueryGenerator",
    "OllamaUnavailableError",
    "RetryConfig",
    "VariationEngine",
    "assign_splits",
    "derive_labels",
    "expand_matrix",
    "validate_spec_consistency",
]
