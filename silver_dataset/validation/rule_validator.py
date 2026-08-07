"""Business rule validation for Silver Dataset cases.

Validates semantic consistency rules beyond schema conformance:
- Route/tool/action combination validity
- Fixture reference integrity
- Item ID existence within referenced fixtures
"""

from __future__ import annotations

from silver_dataset.models.case import (
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
    SilverCase,
)
from silver_dataset.models.fixtures import FixtureRegistry


class RuleValidator:
    """Validates business rules beyond schema conformance.

    Checks performed:
    1. Route/tool/action consistency (redundant with model_validator but
       provides separate error reporting layer for the validation pipeline).
    2. Fixture reference integrity: tool_output_fixture_id must exist.
    3. Item ID existence: all IDs in expected/acceptable/forbidden item lists
       must be present in the referenced fixture.
    """

    def __init__(self, fixture_registry: FixtureRegistry) -> None:
        """Initialize with a fixture registry for reference checks.

        Args:
            fixture_registry: Registry to verify fixture existence and item IDs.
        """
        self._registry = fixture_registry

    def validate(self, case: SilverCase) -> list[str]:
        """Validate business rules for a parsed SilverCase.

        Args:
            case: A valid SilverCase instance (schema-validated).

        Returns:
            List of rule violation messages. Empty list means all rules pass.
        """
        violations: list[str] = []

        # Rule 1: Route/tool/action consistency
        violations.extend(self._check_route_tool_action(case))

        # Rule 2: Fixture reference integrity
        violations.extend(self._check_fixture_reference(case))

        # Rule 3: Item ID existence in fixture
        violations.extend(self._check_item_ids(case))

        return violations

    def _check_route_tool_action(self, case: SilverCase) -> list[str]:
        """Check route/tool/action combination validity."""
        violations: list[str] = []

        if case.expected_route in (
            ExpectedRoute.clarification,
            ExpectedRoute.out_of_scope,
        ) and case.expected_tool != ExpectedTool.none:
            violations.append(
                f"Route '{case.expected_route.value}' requires tool 'none', "
                f"got '{case.expected_tool.value}'"
            )

        if (
            case.expected_action == ExpectedAction.call_tool
            and case.expected_tool == ExpectedTool.none
        ):
            violations.append(
                "Action 'call_tool' requires a non-'none' tool"
            )

        return violations

    def _check_fixture_reference(self, case: SilverCase) -> list[str]:
        """Check that tool_output_fixture_id references an existing fixture."""
        violations: list[str] = []

        if case.tool_output_fixture_id is not None:
            if not self._registry.fixture_exists(case.tool_output_fixture_id):
                violations.append(
                    f"Fixture '{case.tool_output_fixture_id}' does not exist "
                    f"in the fixture registry"
                )

        return violations

    def _check_item_ids(self, case: SilverCase) -> list[str]:
        """Check that all item IDs exist in the referenced fixture."""
        violations: list[str] = []

        if case.tool_output_fixture_id is None:
            # No fixture reference — skip item ID checks but flag if items are listed
            all_items = (
                case.expected_selected_items
                + case.acceptable_selected_items
                + case.forbidden_selected_items
            )
            if all_items:
                violations.append(
                    "Case has item ID references but no tool_output_fixture_id"
                )
            return violations

        available_ids = self._registry.get_item_ids(case.tool_output_fixture_id)

        # If fixture doesn't exist or has no results, available_ids is empty.
        # Fixture existence is already checked above, so here we just check items.
        for field_name, item_list in [
            ("expected_selected_items", case.expected_selected_items),
            ("acceptable_selected_items", case.acceptable_selected_items),
            ("forbidden_selected_items", case.forbidden_selected_items),
        ]:
            for item_id in item_list:
                if item_id not in available_ids:
                    violations.append(
                        f"Item ID '{item_id}' in '{field_name}' not found "
                        f"in fixture '{case.tool_output_fixture_id}'"
                    )

        return violations
