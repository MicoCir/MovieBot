"""Property-based tests for JSON extraction from LLM output.

Feature: silver-dataset-generation
Properties tested:
- Property 20: Extra JSON fields ignored during parsing
- Property 21: JSON extraction from noisy LLM output

The _extract_json method SHALL:
- Successfully extract valid fields and discard extras without error (Property 20)
- Extract JSON blocks surrounded by arbitrary preamble/postamble text (Property 21)
"""

import json

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from silver_dataset.generation.query_generator import OllamaQueryGenerator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# The generator instance used to access _extract_json
_generator = OllamaQueryGenerator()


# Strategy for valid JSON objects with the expected schema fields
@st.composite
def valid_json_with_extras(draw):
    """Generate a valid JSON string with required fields plus arbitrary extra fields."""
    # Required fields
    query = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(
        whitelist_categories=("L", "Nd", "Z"),
        whitelist_characters=" ,.!?'-"
    )))
    conversation_context = draw(st.just([]) | st.just([{"role": "user", "content": "hi"}]))

    base_obj = {
        "query": query,
        "conversation_context": conversation_context,
    }

    # Add extra fields that should be ignored
    num_extras = draw(st.integers(min_value=1, max_value=5))
    for i in range(num_extras):
        key = draw(st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="_"),
        ))
        # Avoid overwriting required fields
        if key not in ("query", "conversation_context"):
            value = draw(st.one_of(
                st.text(min_size=0, max_size=50),
                st.integers(min_value=-1000, max_value=1000),
                st.booleans(),
                st.none(),
            ))
            base_obj[key] = value

    return json.dumps(base_obj, ensure_ascii=False)


@st.composite
def noisy_json_strategy(draw):
    """Generate a JSON block surrounded by arbitrary preamble and postamble text."""
    # Core valid JSON
    query = draw(st.text(min_size=1, max_size=80, alphabet=st.characters(
        whitelist_categories=("L", "Nd", "Z"),
        whitelist_characters=" ,.!?'-"
    )))
    obj = {"query": query, "conversation_context": []}
    json_str = json.dumps(obj, ensure_ascii=False)

    # Preamble: text before the JSON (simulating LLM chatter)
    preamble_options = [
        "Here is the generated query:\n",
        "Sure! I'll generate that for you.\n\n",
        "Based on the context provided, here's my response:\n",
        "",
        "Let me think about this...\n\nOkay, here it is:\n",
    ]
    preamble = draw(st.sampled_from(preamble_options))

    # Postamble: text after the JSON
    postamble_options = [
        "",
        "\n\nI hope this helps!",
        "\nLet me know if you need anything else.",
        "\n\nNote: This is a single-turn query.",
    ]
    postamble = draw(st.sampled_from(postamble_options))

    # Wrapping style
    wrap_style = draw(st.sampled_from(["plain", "code_block", "json_code_block"]))

    if wrap_style == "code_block":
        raw = f"{preamble}```\n{json_str}\n```{postamble}"
    elif wrap_style == "json_code_block":
        raw = f"{preamble}```json\n{json_str}\n```{postamble}"
    else:
        raw = f"{preamble}{json_str}{postamble}"

    return raw, obj


# ---------------------------------------------------------------------------
# Property 20: Extra JSON fields ignored during parsing
# **Validates: Requirement 11.1**
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(json_str=valid_json_with_extras())
@settings(max_examples=100)
def test_extra_json_fields_are_ignored(json_str: str):
    """For any valid JSON with extra fields beyond the expected schema,
    _extract_json SHALL successfully extract valid fields and discard extras
    without raising an error."""
    result = _generator._extract_json(json_str)

    # Must be a dict
    assert isinstance(result, dict)

    # Required fields must be present
    assert "query" in result
    assert "conversation_context" in result

    # The query value should match what was in the JSON
    original = json.loads(json_str)
    assert result["query"] == original["query"]
    assert result["conversation_context"] == original["conversation_context"]


@pytest.mark.property
@given(json_str=valid_json_with_extras())
@settings(max_examples=100)
def test_extra_fields_preserved_in_raw_dict(json_str: str):
    """The raw dict returned by _extract_json MAY contain extra fields
    (they are simply unused by _build_case), but it SHALL NOT error."""
    result = _generator._extract_json(json_str)

    # Parse the original to compare
    original = json.loads(json_str)

    # All keys from original should be present in result
    for key in original:
        assert key in result, f"Key '{key}' missing from extracted result"


# ---------------------------------------------------------------------------
# Property 21: JSON extraction from noisy LLM output
# **Validates: Requirement 11.2**
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(data=noisy_json_strategy())
@settings(max_examples=100)
def test_json_extraction_from_noisy_output(data: tuple[str, dict]):
    """For any LLM response containing a valid JSON block surrounded by
    arbitrary preamble or postamble text, _extract_json SHALL successfully
    extract and return the JSON content."""
    raw_response, expected_obj = data

    result = _generator._extract_json(raw_response)

    # Must be a dict
    assert isinstance(result, dict)

    # Required fields must match
    assert result["query"] == expected_obj["query"]
    assert result["conversation_context"] == expected_obj["conversation_context"]


@pytest.mark.property
@given(data=noisy_json_strategy())
@settings(max_examples=100)
def test_json_extraction_returns_dict_type(data: tuple[str, dict]):
    """For any noisy LLM output with embedded JSON, _extract_json SHALL
    return a dict (not a list, string, or other JSON type)."""
    raw_response, _ = data

    result = _generator._extract_json(raw_response)
    assert isinstance(result, dict)
