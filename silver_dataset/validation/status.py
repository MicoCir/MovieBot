"""Validation status assignment logic.

Aggregates results from schema validation, rule validation, and critic
assessment to determine the overall automatic_validation_status for a case.
"""

from __future__ import annotations

from silver_dataset.models.case import ValidationStatus
from silver_dataset.validation.critic import CriticResult


def assign_validation_status(
    schema_errors: list[str],
    rule_violations: list[str],
    critic_result: CriticResult | None = None,
) -> ValidationStatus:
    """Aggregate validation results into a single automatic_validation_status.

    Decision logic:
    - Any schema error → failed
    - Any rule violation → failed
    - Critic status "failed" → failed
    - Critic status "warning" → warning
    - All pass → passed

    Args:
        schema_errors: Errors from SchemaValidator (empty means schema is valid).
        rule_violations: Violations from RuleValidator (empty means rules pass).
        critic_result: Optional CriticResult from the LLM critic assessment.
            If None, critic is treated as passed (not evaluated).

    Returns:
        The aggregate ValidationStatus enum value.
    """
    # Any schema or rule failure means the case is invalid
    if schema_errors:
        return ValidationStatus.failed
    if rule_violations:
        return ValidationStatus.failed

    # Check critic result if provided
    if critic_result is not None:
        if critic_result.status == "failed":
            return ValidationStatus.failed
        if critic_result.status == "warning":
            return ValidationStatus.warning

    return ValidationStatus.passed
