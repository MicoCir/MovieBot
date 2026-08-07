"""Human-readable formatting for SilverCase instances.

Provides a PrettyPrinter class that formats cases into structured,
readable text for manual inspection and debugging.
"""

from silver_dataset.models.case import SilverCase


class PrettyPrinter:
    """Human-readable formatter for SilverCase instances."""

    DOUBLE_LINE = "═" * 55
    SINGLE_LINE = "─" * 55

    def format_case(self, case: SilverCase) -> str:
        """Format a single case for human inspection."""
        lines: list[str] = []

        # Header
        lines.append(self.DOUBLE_LINE)
        lines.append(
            f"CASE: {case.case_id} [{case.suite.value} / {case.split.value}]"
        )
        lines.append(self.DOUBLE_LINE)

        # Query and basic info
        lines.append(f"Query:      {case.query}")
        lines.append(f"Language:   {case.language} → {case.response_language}")
        lines.append(
            f"Family:     {case.scenario_family} / {case.scenario_type}"
        )
        lines.append(f"Difficulty: {case.difficulty.value}")

        # Expectations
        lines.append("")
        lines.append(f"─── Expectations ───")
        lines.append(f"Route:      {case.expected_route.value}")
        lines.append(f"Tool:       {case.expected_tool.value}")
        lines.append(f"Action:     {case.expected_action.value}")

        # Items
        lines.append("")
        lines.append(f"─── Items ───")
        lines.append(f"Expected:   {case.expected_selected_items}")
        lines.append(f"Acceptable: {case.acceptable_selected_items}")
        lines.append(f"Forbidden:  {case.forbidden_selected_items}")

        # Grounding
        lines.append("")
        lines.append(f"─── Grounding ───")
        lines.append(f"Required facts:   {len(case.required_facts)}")
        lines.append(f"Forbidden claims: {len(case.forbidden_claims)}")

        # Metadata
        lines.append("")
        lines.append(f"─── Metadata ───")
        lines.append(
            f"Status:     {case.automatic_validation_status.value} "
            f"({case.review_status.value.replace('_', ' ')})"
        )
        lines.append(f"Tags:       {case.tags}")
        lines.append(f"Seed:       {case.seed_scenario_id}")
        ts = case.generation_metadata.timestamp.isoformat()
        model = case.generation_metadata.model
        pv = case.generation_metadata.prompt_version
        lines.append(f"Generated:  {ts} by {model} ({pv})")
        lines.append(self.DOUBLE_LINE)

        return "\n".join(lines)

    def format_cases(self, cases: list[SilverCase]) -> str:
        """Format multiple cases, separated by blank lines."""
        return "\n\n".join(self.format_case(case) for case in cases)
