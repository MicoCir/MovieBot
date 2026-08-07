"""Quick verification test for read_jsonl and ParseError."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from silver_dataset.io.jsonl import ParseError, read_jsonl, write_jsonl
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


def _make_case(case_id: str = "test-001") -> SilverCase:
    """Create a minimal valid SilverCase for testing."""
    return SilverCase(
        case_id=case_id,
        dataset_version="1.0.0",
        suite=Suite.e2e_routing_silver,
        split=Split.dev,
        scenario_family="trending_basic",
        scenario_type="happy_path",
        query="What movies are trending today?",
        language="en",
        response_language="en",
        expected_route=ExpectedRoute.trending,
        expected_tool=ExpectedTool.tmdb_trending,
        expected_action=ExpectedAction.call_tool,
        expected_response_type="list",
        difficulty=Difficulty.easy,
        seed_scenario_id="seed-001",
        generation_metadata=GenerationMetadata(
            method="template",
            model="qwen3.5:27b",
            prompt_version="v1",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            batch_id="batch-001",
        ),
    )


@pytest.mark.silver
class TestReadJsonl:
    """Tests for read_jsonl function."""

    def test_reads_valid_jsonl(self, tmp_path: Path):
        """Valid JSONL lines are parsed into SilverCase instances."""
        file_path = tmp_path / "valid.jsonl"
        cases = [_make_case("case-001"), _make_case("case-002")]
        write_jsonl(cases, file_path)

        result_cases, errors = read_jsonl(file_path)

        assert len(result_cases) == 2
        assert len(errors) == 0
        assert result_cases[0].case_id == "case-001"
        assert result_cases[1].case_id == "case-002"

    def test_captures_invalid_json_as_parse_error(self, tmp_path: Path):
        """Invalid JSON lines are captured as ParseError without stopping."""
        file_path = tmp_path / "mixed.jsonl"
        valid_case = _make_case("case-001")

        with open(file_path, "w", encoding="utf-8") as f:
            # Line 1: valid case
            f.write(valid_case.model_dump_json() + "\n")
            # Line 2: invalid JSON
            f.write("this is not valid json\n")
            # Line 3: another valid case
            f.write(valid_case.model_dump_json() + "\n")

        result_cases, errors = read_jsonl(file_path)

        assert len(result_cases) == 2
        assert len(errors) == 1
        assert errors[0].line_number == 2
        assert errors[0].raw_content == "this is not valid json"
        assert "Expecting value" in errors[0].error or "JSON" in errors[0].error

    def test_captures_validation_error(self, tmp_path: Path):
        """Valid JSON that fails Pydantic validation is captured as ParseError."""
        file_path = tmp_path / "bad_schema.jsonl"
        valid_case = _make_case("case-001")

        with open(file_path, "w", encoding="utf-8") as f:
            # Line 1: valid case
            f.write(valid_case.model_dump_json() + "\n")
            # Line 2: valid JSON but invalid SilverCase (missing required fields)
            f.write(json.dumps({"case_id": "incomplete"}) + "\n")

        result_cases, errors = read_jsonl(file_path)

        assert len(result_cases) == 1
        assert result_cases[0].case_id == "case-001"
        assert len(errors) == 1
        assert errors[0].line_number == 2
        assert "incomplete" in errors[0].raw_content

    def test_skips_empty_lines(self, tmp_path: Path):
        """Empty lines and whitespace-only lines are skipped."""
        file_path = tmp_path / "with_blanks.jsonl"
        valid_case = _make_case("case-001")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n")  # empty line
            f.write(valid_case.model_dump_json() + "\n")
            f.write("   \n")  # whitespace-only line
            f.write(valid_case.model_dump_json() + "\n")

        result_cases, errors = read_jsonl(file_path)

        assert len(result_cases) == 2
        assert len(errors) == 0

    def test_continues_after_errors(self, tmp_path: Path):
        """Processing continues after encountering errors."""
        file_path = tmp_path / "errors.jsonl"
        valid_case = _make_case("case-001")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("bad line 1\n")
            f.write("{}\n")  # valid JSON but invalid SilverCase
            f.write(valid_case.model_dump_json() + "\n")
            f.write("bad line 4\n")
            f.write(valid_case.model_dump_json() + "\n")

        result_cases, errors = read_jsonl(file_path)

        assert len(result_cases) == 2
        assert len(errors) == 3
        assert errors[0].line_number == 1
        assert errors[1].line_number == 2
        assert errors[2].line_number == 4


@pytest.mark.silver
class TestParseError:
    """Tests for ParseError dataclass."""

    def test_fields(self):
        """ParseError holds line_number, error, and raw_content."""
        err = ParseError(line_number=5, error="some error", raw_content="bad data")
        assert err.line_number == 5
        assert err.error == "some error"
        assert err.raw_content == "bad data"

    def test_equality(self):
        """ParseError instances with same fields are equal (dataclass)."""
        err1 = ParseError(line_number=1, error="err", raw_content="x")
        err2 = ParseError(line_number=1, error="err", raw_content="x")
        assert err1 == err2
