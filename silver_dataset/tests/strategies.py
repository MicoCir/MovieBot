"""Custom Hypothesis strategies for silver_dataset models.

This module contains composite strategies for generating valid instances of:
- SilverCase
- GenerationMetadata
- LatentSpecification (valid and inconsistent)

These strategies are designed to:
1. Produce valid model instances that satisfy Pydantic constraints.
2. Respect enum value sets and inter-field consistency rules
   (e.g., route/tool/action combinations).
3. Be composable so property tests can focus on specific invariants.

Usage (from test modules):
    from silver_dataset.tests.strategies import silver_case_strategy
    from silver_dataset.tests.strategies import latent_spec_strategy
    from silver_dataset.tests.strategies import inconsistent_latent_spec_strategy
"""

from hypothesis import strategies as st
from hypothesis.strategies import composite

from silver_dataset.models.case import (
    Difficulty,
    ExpectedAction,
    ExpectedRoute,
    ExpectedTool,
    GenerationMetadata,
    ReviewStatus,
    SilverCase,
    Split,
    Suite,
    ValidationStatus,
)
from silver_dataset.models.latent_spec import LatentSpecification


@composite
def generation_metadata_strategy(draw):
    """Generate a valid GenerationMetadata instance."""
    return GenerationMetadata(
        method=draw(st.text(min_size=1, max_size=50)),
        model=draw(st.text(min_size=1, max_size=50)),
        prompt_version=draw(st.text(min_size=1, max_size=50)),
        timestamp=draw(st.datetimes()),
        batch_id=draw(st.text(min_size=1, max_size=50)),
        variation_type=draw(st.none() | st.text(min_size=1, max_size=50)),
    )


@composite
def silver_case_strategy(draw):
    """Generate a valid SilverCase instance respecting model_validator constraints.

    Consistency rules enforced:
    - When expected_route is 'clarification' or 'out_of_scope', expected_tool must be 'none'
    - When expected_action is 'call_tool', expected_tool must NOT be 'none'
    Combined: route=clarification/out_of_scope implies tool=none implies action != call_tool
    """
    expected_route = draw(st.sampled_from(ExpectedRoute))

    if expected_route in (ExpectedRoute.clarification, ExpectedRoute.out_of_scope):
        # Route requires tool=none, which in turn means action cannot be call_tool
        expected_tool = ExpectedTool.none
        expected_action = draw(
            st.sampled_from(
                [a for a in ExpectedAction if a != ExpectedAction.call_tool]
            )
        )
    else:
        expected_action = draw(st.sampled_from(ExpectedAction))
        if expected_action == ExpectedAction.call_tool:
            # Action requires a real tool (not none)
            expected_tool = draw(
                st.sampled_from(
                    [t for t in ExpectedTool if t != ExpectedTool.none]
                )
            )
        else:
            # No constraint — any tool value is valid
            expected_tool = draw(st.sampled_from(ExpectedTool))

    return SilverCase(
        case_id=draw(st.text(min_size=1, max_size=50)),
        dataset_version=draw(st.text(min_size=1, max_size=50)),
        suite=draw(st.sampled_from(Suite)),
        split=draw(st.sampled_from(Split)),
        scenario_family=draw(st.text(min_size=1, max_size=50)),
        scenario_type=draw(st.text(min_size=1, max_size=50)),
        query=draw(st.text(min_size=1, max_size=50)),
        conversation_context=draw(st.just([])),
        language=draw(st.text(min_size=1, max_size=50)),
        response_language=draw(st.text(min_size=1, max_size=50)),
        expected_route=expected_route,
        expected_tool=expected_tool,
        expected_action=expected_action,
        expected_tool_request=draw(st.none() | st.just({})),
        user_constraints=draw(st.just({})),
        tool_output_fixture_id=draw(st.none() | st.text(min_size=1, max_size=50)),
        expected_selected_items=draw(st.lists(st.text(min_size=1, max_size=50), max_size=3)),
        acceptable_selected_items=draw(st.lists(st.text(min_size=1, max_size=50), max_size=3)),
        forbidden_selected_items=draw(st.lists(st.text(min_size=1, max_size=50), max_size=3)),
        required_facts=draw(st.just([])),
        optional_facts=draw(st.just([])),
        forbidden_claims=draw(st.lists(st.text(min_size=1, max_size=50), max_size=3)),
        expected_response_type=draw(st.text(min_size=1, max_size=50)),
        difficulty=draw(st.sampled_from(Difficulty)),
        tags=draw(st.lists(st.text(min_size=1, max_size=50), max_size=5)),
        seed_scenario_id=draw(st.text(min_size=1, max_size=50)),
        generation_metadata=draw(generation_metadata_strategy()),
        automatic_validation_status=draw(st.sampled_from(ValidationStatus)),
        review_status=draw(st.sampled_from(ReviewStatus)),
    )


@composite
def latent_spec_strategy(draw):
    """Generate a valid LatentSpecification instance respecting all consistency rules.

    Consistency rules enforced:
    - Route clarification/out_of_scope requires tool=none
    - Action call_tool requires tool != none
    - Route out_of_scope requires action=return_out_of_scope
    - Route clarification requires action=ask_clarifying_question
    - Suite/tool consistency: tmdb_agent_silver + call_tool requires tmdb_trending;
      netflix_agent_silver + call_tool requires netflix_search
    - Fixture reference: call_tool/answer_from_tool_output require fixture_id;
      return_out_of_scope/ask_clarifying_question require fixture_id=None
    """
    route = draw(st.sampled_from(ExpectedRoute))

    if route == ExpectedRoute.out_of_scope:
        tool = ExpectedTool.none
        action = ExpectedAction.return_out_of_scope
    elif route == ExpectedRoute.clarification:
        tool = ExpectedTool.none
        action = ExpectedAction.ask_clarifying_question
    else:
        # Routes trending/netflix allow all actions
        action = draw(st.sampled_from(ExpectedAction))
        if action == ExpectedAction.call_tool:
            tool = draw(
                st.sampled_from(
                    [t for t in ExpectedTool if t != ExpectedTool.none]
                )
            )
        else:
            tool = draw(st.sampled_from(ExpectedTool))

    # Suite selection with consistency for call_tool
    if action == ExpectedAction.call_tool:
        if tool == ExpectedTool.tmdb_trending:
            suite = Suite.tmdb_agent_silver
        elif tool == ExpectedTool.netflix_search:
            suite = Suite.netflix_agent_silver
        else:
            suite = draw(st.sampled_from(Suite))
    else:
        suite = draw(st.sampled_from(Suite))

    # Fixture reference consistency
    if action in (ExpectedAction.call_tool, ExpectedAction.answer_from_tool_output):
        fixture_id = draw(st.text(min_size=1, max_size=30))
    elif action in (ExpectedAction.return_out_of_scope, ExpectedAction.ask_clarifying_question):
        fixture_id = None
    else:
        fixture_id = draw(st.none() | st.text(min_size=1, max_size=30))

    return LatentSpecification(
        spec_id=draw(st.text(min_size=1, max_size=30)),
        suite=suite,
        scenario_family=draw(st.text(min_size=1, max_size=30)),
        scenario_type=draw(st.text(min_size=1, max_size=30)),
        route=route,
        tool=tool,
        action=action,
        language=draw(st.sampled_from(["en", "es"])),
        response_language=draw(st.sampled_from(["en", "es"])),
        difficulty=draw(st.sampled_from(Difficulty)),
        tool_request_template=draw(st.none() | st.just({"key": "value"})),
        user_constraints=draw(st.just({})),
        fixture_id=fixture_id,
        variation_type=draw(st.none() | st.sampled_from(["paraphrase", "typo", "translation", "code-switch"])),
        seed_scenario_id=draw(st.none() | st.text(min_size=1, max_size=30)),
        tags=draw(st.lists(st.text(min_size=1, max_size=20), max_size=3)),
    )


@composite
def inconsistent_latent_spec_strategy(draw):
    """Generate a LatentSpecification with known contradictions in route/tool/action.

    Contradiction types generated:
    1. Route clarification/out_of_scope with tool != none
    2. Action call_tool with tool = none
    3. Route out_of_scope with action != return_out_of_scope
    4. Route clarification with action != ask_clarifying_question
    """
    contradiction_type = draw(st.sampled_from([1, 2, 3, 4]))

    if contradiction_type == 1:
        # Route clarification/out_of_scope with tool != none
        route = draw(st.sampled_from([ExpectedRoute.clarification, ExpectedRoute.out_of_scope]))
        tool = draw(st.sampled_from([ExpectedTool.tmdb_trending, ExpectedTool.netflix_search]))
        action = draw(st.sampled_from(ExpectedAction))
    elif contradiction_type == 2:
        # Action call_tool with tool = none
        route = draw(st.sampled_from([ExpectedRoute.trending, ExpectedRoute.netflix]))
        tool = ExpectedTool.none
        action = ExpectedAction.call_tool
    elif contradiction_type == 3:
        # Route out_of_scope with action != return_out_of_scope
        route = ExpectedRoute.out_of_scope
        tool = ExpectedTool.none  # Keep tool consistent to isolate this violation
        action = draw(
            st.sampled_from(
                [a for a in ExpectedAction if a != ExpectedAction.return_out_of_scope]
            )
        )
    else:
        # Route clarification with action != ask_clarifying_question
        route = ExpectedRoute.clarification
        tool = ExpectedTool.none  # Keep tool consistent to isolate this violation
        action = draw(
            st.sampled_from(
                [a for a in ExpectedAction if a != ExpectedAction.ask_clarifying_question]
            )
        )

    suite = draw(st.sampled_from(Suite))
    fixture_id = draw(st.none() | st.text(min_size=1, max_size=30))

    return LatentSpecification(
        spec_id=draw(st.text(min_size=1, max_size=30)),
        suite=suite,
        scenario_family=draw(st.text(min_size=1, max_size=30)),
        scenario_type=draw(st.text(min_size=1, max_size=30)),
        route=route,
        tool=tool,
        action=action,
        language=draw(st.sampled_from(["en", "es"])),
        response_language=draw(st.sampled_from(["en", "es"])),
        difficulty=draw(st.sampled_from(Difficulty)),
        tool_request_template=draw(st.none() | st.just({"key": "value"})),
        user_constraints=draw(st.just({})),
        fixture_id=fixture_id,
        variation_type=draw(st.none() | st.sampled_from(["paraphrase", "typo", "translation", "code-switch"])),
        seed_scenario_id=draw(st.none() | st.text(min_size=1, max_size=30)),
        tags=draw(st.lists(st.text(min_size=1, max_size=20), max_size=3)),
    )
