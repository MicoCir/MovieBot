"""Property-based tests for generation metadata completeness.

Feature: silver-dataset-generation
Property tested:
- Property 11: Generation metadata completeness

For any generated SilverCase, generation_metadata SHALL contain non-empty model,
prompt_version, valid timestamp, non-empty batch_id.
"""

from datetime import datetime

import pytest
from hypothesis import given, settings

from silver_dataset.models.case import GenerationMetadata, SilverCase
from silver_dataset.tests.strategies import silver_case_strategy


# ---------------------------------------------------------------------------
# Property 11: Generation metadata completeness
# **Validates: Requirements 4.6, 11.5**
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_generation_metadata_has_non_empty_model(case: SilverCase):
    """For any generated SilverCase, generation_metadata.model SHALL be non-empty.

    The strategy guarantees min_size=1, so model always has at least 1 character.
    """
    assert case.generation_metadata.model is not None
    assert len(case.generation_metadata.model) > 0


@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_generation_metadata_has_non_empty_prompt_version(case: SilverCase):
    """For any generated SilverCase, generation_metadata.prompt_version SHALL be non-empty."""
    assert case.generation_metadata.prompt_version is not None
    assert len(case.generation_metadata.prompt_version) > 0


@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_generation_metadata_has_valid_timestamp(case: SilverCase):
    """For any generated SilverCase, generation_metadata.timestamp SHALL be a valid datetime."""
    ts = case.generation_metadata.timestamp
    assert isinstance(ts, datetime), (
        f"generation_metadata.timestamp is not a datetime: {type(ts)}"
    )


@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_generation_metadata_has_non_empty_batch_id(case: SilverCase):
    """For any generated SilverCase, generation_metadata.batch_id SHALL be non-empty."""
    assert case.generation_metadata.batch_id is not None
    assert len(case.generation_metadata.batch_id) > 0


@pytest.mark.property
@given(case=silver_case_strategy())
@settings(max_examples=100)
def test_generation_metadata_completeness_combined(case: SilverCase):
    """For any generated SilverCase, ALL required generation_metadata fields
    SHALL be present and non-empty simultaneously.

    The silver_case_strategy generates text with min_size=1, guaranteeing
    that the string fields always contain at least one character.
    """
    meta = case.generation_metadata

    # All required fields must be non-empty (at least 1 character)
    assert meta.model and len(meta.model) > 0, "model is empty"
    assert meta.prompt_version and len(meta.prompt_version) > 0, "prompt_version is empty"
    assert meta.batch_id and len(meta.batch_id) > 0, "batch_id is empty"
    assert isinstance(meta.timestamp, datetime), "timestamp is not a datetime"

    # method should also be non-empty (always set to generation method)
    assert meta.method and len(meta.method) > 0, "method is empty"
