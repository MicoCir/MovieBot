"""Validation pipeline for the Silver Dataset.

Provides schema validation, business rule checks, LLM-based quality criticism,
deduplication (exact, normalized, and semantic), and status assignment logic.
"""

from silver_dataset.validation.critic import Critic, CriticResult
from silver_dataset.validation.deduplicator import Deduplicator, DuplicatePair
from silver_dataset.validation.rule_validator import RuleValidator
from silver_dataset.validation.schema_validator import SchemaValidator
from silver_dataset.validation.status import assign_validation_status

__all__ = [
    "Critic",
    "CriticResult",
    "Deduplicator",
    "DuplicatePair",
    "RuleValidator",
    "SchemaValidator",
    "assign_validation_status",
]
