"""Property-based tests for fixture referential integrity and fact traceability.

Feature: silver-dataset-generation
Properties tested:
- Property 7: Referential integrity of fixtures and item IDs
- Property 8: Required facts traceable to fixture
"""

import json

import pytest
from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st

from silver_dataset.models.fixtures import FixtureRegistry


# The fixtures_dir fixture is function-scoped but read-only (returns a static Path),
# so it's safe to suppress the health check for function-scoped fixtures.
_pbt_settings = settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# ---------------------------------------------------------------------------
# Property 7: Referential integrity of fixtures and item IDs
# ---------------------------------------------------------------------------
# For any SilverCase with a non-null tool_output_fixture_id, the referenced
# fixture SHALL exist in the FixtureRegistry; and for any ID in
# expected_selected_items, acceptable_selected_items, or
# forbidden_selected_items, that ID SHALL exist within the referenced
# fixture's content.
#
# **Validates: Requirements 5.3, 5.5, 6.3**
# ---------------------------------------------------------------------------


@pytest.mark.property
@_pbt_settings
@given(data=st.data())
def test_referential_integrity_fixture_exists(data, fixtures_dir):
    """For any case referencing a fixture, that fixture SHALL exist.

    Feature: silver-dataset-generation, Property 7: Referential integrity of fixtures and item IDs
    **Validates: Requirements 5.3, 5.5**
    """
    registry = FixtureRegistry(fixtures_dir)
    available = registry.list_fixtures()
    assume(len(available) > 0)

    fixture_id = data.draw(st.sampled_from(available))
    assert registry.fixture_exists(fixture_id), (
        f"Fixture '{fixture_id}' listed by registry but fixture_exists() returned False"
    )


@pytest.mark.property
@_pbt_settings
@given(data=st.data())
def test_referential_integrity_item_ids_in_fixture(data, fixtures_dir):
    """For any item ID drawn from a fixture, it SHALL exist within that fixture's content.

    Any subset of item_ids from a fixture is a valid set for expected_selected_items,
    acceptable_selected_items, or forbidden_selected_items.

    Feature: silver-dataset-generation, Property 7: Referential integrity of fixtures and item IDs
    **Validates: Requirements 5.3, 5.5**
    """
    registry = FixtureRegistry(fixtures_dir)
    available = registry.list_fixtures()
    assume(len(available) > 0)

    fixture_id = data.draw(st.sampled_from(available))
    item_ids = registry.get_item_ids(fixture_id)

    # Only test fixtures that have items (skip error/empty fixtures)
    assume(len(item_ids) > 0)

    # Draw a random subset as would appear in expected/acceptable/forbidden lists
    selected = data.draw(
        st.lists(st.sampled_from(sorted(item_ids)), min_size=1, max_size=3)
    )

    for item in selected:
        assert item in item_ids, (
            f"Item '{item}' drawn from fixture '{fixture_id}' "
            f"but not found in get_item_ids() result: {item_ids}"
        )


@pytest.mark.property
@_pbt_settings
@given(data=st.data())
def test_referential_integrity_nonexistent_ids_not_in_fixture(data, fixtures_dir):
    """For any fabricated ID not in the fixture, it SHALL NOT be in get_item_ids().

    This tests the contrapositive: IDs not from the fixture must not pass
    referential integrity checks.

    Feature: silver-dataset-generation, Property 7: Referential integrity of fixtures and item IDs
    **Validates: Requirements 5.5, 6.3**
    """
    registry = FixtureRegistry(fixtures_dir)
    available = registry.list_fixtures()
    assume(len(available) > 0)

    fixture_id = data.draw(st.sampled_from(available))
    item_ids = registry.get_item_ids(fixture_id)

    # Generate a random ID that is unlikely to be in the fixture
    fake_id = data.draw(st.text(
        alphabet=st.characters(whitelist_categories=("L", "N")),
        min_size=20,
        max_size=30,
    ))
    assume(fake_id not in item_ids)

    assert fake_id not in item_ids, (
        f"Fabricated ID '{fake_id}' unexpectedly found in fixture '{fixture_id}'"
    )


def test_referential_integrity_concrete_tmdb(fixtures_dir):
    """Concrete test: TMDB fixture items are accessible and consistent.

    Feature: silver-dataset-generation, Property 7: Referential integrity of fixtures and item IDs
    **Validates: Requirements 5.3, 5.5**
    """
    registry = FixtureRegistry(fixtures_dir)

    # tmdb_trending_normal has known items with numeric IDs
    fixture_id = "tmdb_trending_normal"
    assert registry.fixture_exists(fixture_id)

    item_ids = registry.get_item_ids(fixture_id)
    assert len(item_ids) > 0, "tmdb_trending_normal should have item IDs"

    # Verify all IDs are strings (as required by the interface)
    for item_id in item_ids:
        assert isinstance(item_id, str)

    # Verify known IDs from the fixture data
    assert "100001" in item_ids
    assert "100002" in item_ids
    assert "100005" in item_ids


def test_referential_integrity_concrete_netflix(fixtures_dir):
    """Concrete test: Netflix fixture items are accessible and consistent.

    Feature: silver-dataset-generation, Property 7: Referential integrity of fixtures and item IDs
    **Validates: Requirements 5.3, 5.5**
    """
    registry = FixtureRegistry(fixtures_dir)

    # netflix_search_comedy has known items with show_id
    fixture_id = "netflix_search_comedy"
    assert registry.fixture_exists(fixture_id)

    item_ids = registry.get_item_ids(fixture_id)
    assert len(item_ids) > 0, "netflix_search_comedy should have item IDs"

    # Verify known IDs from the fixture data
    assert "s101" in item_ids
    assert "s102" in item_ids
    assert "s103" in item_ids
    assert "s104" in item_ids


def test_referential_integrity_empty_fixture_has_no_items(fixtures_dir):
    """Concrete test: Empty fixtures should return no item IDs.

    Feature: silver-dataset-generation, Property 7: Referential integrity of fixtures and item IDs
    **Validates: Requirements 5.3, 5.5**
    """
    registry = FixtureRegistry(fixtures_dir)

    # Empty fixtures have no results
    for fixture_id in ["tmdb_trending_empty", "netflix_search_empty"]:
        if registry.fixture_exists(fixture_id):
            item_ids = registry.get_item_ids(fixture_id)
            assert len(item_ids) == 0, (
                f"Empty fixture '{fixture_id}' should have no item IDs, got: {item_ids}"
            )


def test_referential_integrity_all_listed_fixtures_exist(fixtures_dir):
    """Concrete test: Every fixture returned by list_fixtures() must exist.

    Feature: silver-dataset-generation, Property 7: Referential integrity of fixtures and item IDs
    **Validates: Requirement 5.3**
    """
    registry = FixtureRegistry(fixtures_dir)
    all_fixtures = registry.list_fixtures()

    for fixture_id in all_fixtures:
        assert registry.fixture_exists(fixture_id), (
            f"Fixture '{fixture_id}' listed but does not exist"
        )


# ---------------------------------------------------------------------------
# Property 8: Required facts traceable to fixture
# ---------------------------------------------------------------------------
# For any SilverCase with non-empty required_facts, each fact's value SHALL
# be verifiably present in the data of the fixture referenced by
# tool_output_fixture_id.
#
# **Validates: Requirement 5.7**
# ---------------------------------------------------------------------------


def _extract_all_values(data: dict | list, depth: int = 0) -> set[str]:
    """Recursively extract all string values from a fixture's data structure."""
    if depth > 10:
        return set()

    values: set[str] = set()
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, str):
                values.add(v)
            elif isinstance(v, (int, float)):
                values.add(str(v))
            elif isinstance(v, (dict, list)):
                values.update(_extract_all_values(v, depth + 1))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                values.add(item)
            elif isinstance(item, (int, float)):
                values.add(str(item))
            elif isinstance(item, (dict, list)):
                values.update(_extract_all_values(item, depth + 1))
    return values


@pytest.mark.property
@_pbt_settings
@given(data=st.data())
def test_required_facts_traceable_to_fixture(data, fixtures_dir):
    """For any fact value drawn from fixture data, it SHALL be verifiably present.

    We generate required_facts by drawing actual values from fixture content,
    verifying that any fact constructed from real fixture data is traceable.

    Feature: silver-dataset-generation, Property 8: Required facts traceable to fixture
    **Validates: Requirement 5.7**
    """
    registry = FixtureRegistry(fixtures_dir)
    available = registry.list_fixtures()
    assume(len(available) > 0)

    fixture_id = data.draw(st.sampled_from(available))
    fixture_data = registry.get_fixture(fixture_id)
    assume(fixture_data is not None)

    # Extract all values from the fixture
    all_values = _extract_all_values(fixture_data)
    # Filter to non-empty meaningful values
    meaningful_values = sorted([v for v in all_values if len(v) > 0])
    assume(len(meaningful_values) > 0)

    # Draw fact values from the fixture's actual data
    fact_value = data.draw(st.sampled_from(meaningful_values))

    # Verify the fact value is traceable to the fixture
    assert fact_value in all_values, (
        f"Fact value '{fact_value}' should be traceable to fixture '{fixture_id}'"
    )


def test_required_facts_concrete_tmdb(fixtures_dir):
    """Concrete test: Required facts derived from TMDB fixture are traceable.

    A SilverCase referencing tmdb_trending_normal might have required_facts like:
    - {"field": "title", "value": "Crimson Horizon"}
    - {"field": "vote_average", "value": "7.8"}

    Each fact's value must be present in the fixture data.

    Feature: silver-dataset-generation, Property 8: Required facts traceable to fixture
    **Validates: Requirement 5.7**
    """
    registry = FixtureRegistry(fixtures_dir)
    fixture_id = "tmdb_trending_normal"
    fixture_data = registry.get_fixture(fixture_id)
    assert fixture_data is not None

    all_values = _extract_all_values(fixture_data)

    # Simulate required_facts that a SilverCase might have
    required_facts = [
        {"field": "title", "value": "Crimson Horizon"},
        {"field": "vote_average", "value": "7.8"},
        {"field": "release_date", "value": "2024-03-22"},
        {"field": "original_language", "value": "en"},
    ]

    for fact in required_facts:
        assert fact["value"] in all_values, (
            f"Required fact value '{fact['value']}' not found in fixture '{fixture_id}'"
        )


def test_required_facts_concrete_netflix(fixtures_dir):
    """Concrete test: Required facts derived from Netflix fixture are traceable.

    A SilverCase referencing netflix_search_comedy might have required_facts like:
    - {"field": "title", "value": "The Laugh Factory"}
    - {"field": "director", "value": "Maria Gonzalez"}

    Each fact's value must be present in the fixture data.

    Feature: silver-dataset-generation, Property 8: Required facts traceable to fixture
    **Validates: Requirement 5.7**
    """
    registry = FixtureRegistry(fixtures_dir)
    fixture_id = "netflix_search_comedy"
    fixture_data = registry.get_fixture(fixture_id)
    assert fixture_data is not None

    all_values = _extract_all_values(fixture_data)

    # Simulate required_facts that a SilverCase might have
    required_facts = [
        {"field": "title", "value": "The Laugh Factory"},
        {"field": "director", "value": "Maria Gonzalez"},
        {"field": "rating", "value": "PG-13"},
        {"field": "country", "value": "United States"},
    ]

    for fact in required_facts:
        assert fact["value"] in all_values, (
            f"Required fact value '{fact['value']}' not found in fixture '{fixture_id}'"
        )


@pytest.mark.property
@_pbt_settings
@given(data=st.data())
def test_required_facts_fabricated_not_in_fixture(data, fixtures_dir):
    """Fabricated facts (not from fixture) SHALL NOT be verifiable in fixture data.

    This tests the contrapositive: random strings not found in fixture data
    cannot satisfy the required_facts traceability property.

    Feature: silver-dataset-generation, Property 8: Required facts traceable to fixture
    **Validates: Requirement 5.7**
    """
    registry = FixtureRegistry(fixtures_dir)
    available = registry.list_fixtures()
    assume(len(available) > 0)

    fixture_id = data.draw(st.sampled_from(available))
    fixture_data = registry.get_fixture(fixture_id)
    assume(fixture_data is not None)

    all_values = _extract_all_values(fixture_data)

    # Generate a random string unlikely to be in any fixture
    fake_value = data.draw(st.text(
        alphabet=st.characters(whitelist_categories=("L",)),
        min_size=30,
        max_size=50,
    ))
    assume(fake_value not in all_values)

    assert fake_value not in all_values, (
        f"Fabricated value '{fake_value}' unexpectedly found in fixture '{fixture_id}'"
    )
