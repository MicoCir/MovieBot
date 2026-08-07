"""Schema validation for Silver Dataset cases.

Validates raw dictionaries against the SilverCase Pydantic model,
returning the parsed case and any validation errors encountered.
"""

from __future__ import annotations

from pydantic import ValidationError

from silver_dataset.models.case import SilverCase


class SchemaValidator:
    """Validates cases against the SilverCase Pydantic model.

    This is the first layer of the validation pipeline: it ensures
    that raw dictionaries conform to the required schema structure
    before further business-rule or quality checks.
    """

    def validate(self, raw: dict) -> tuple[SilverCase | None, list[str]]:
        """Validate a raw dictionary against the SilverCase schema.

        Args:
            raw: A dictionary representing a candidate Silver Dataset case.

        Returns:
            A tuple of (parsed_case, errors):
            - parsed_case is a SilverCase instance if validation succeeds, None otherwise.
            - errors is a list of human-readable error messages (empty on success).
        """
        try:
            case = SilverCase.model_validate(raw)
            return case, []
        except ValidationError as e:
            errors = [str(err["msg"]) for err in e.errors()]
            return None, errors
