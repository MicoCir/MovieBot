"""Unit tests for CLI argument parsing and mode switching.

Tests create_parser() and main() for all three commands: generate, validate,
evaluate. Verifies correct argument defaults, required argument enforcement,
and exit code behavior.
"""

import pytest

from silver_dataset.cli import create_parser, main


class TestCreateParserGenerate:
    """Tests for the 'generate' command argument parsing."""

    def test_generate_defaults(self):
        """Test generate command parses with all defaults."""
        parser = create_parser()
        args = parser.parse_args(["generate"])

        assert args.command == "generate"
        assert args.seed == 42
        assert args.output == "silver.jsonl"
        assert args.checkpoint == ".checkpoint.json"
        assert args.version == "silver_v1"
        assert args.batch_id is None

    def test_generate_custom_seed(self):
        """Test generate command with custom seed."""
        parser = create_parser()
        args = parser.parse_args(["generate", "--seed", "123"])

        assert args.seed == 123

    def test_generate_custom_output(self):
        """Test generate command with custom output path."""
        parser = create_parser()
        args = parser.parse_args(["generate", "--output", "my_dataset.jsonl"])

        assert args.output == "my_dataset.jsonl"

    def test_generate_custom_checkpoint(self):
        """Test generate command with custom checkpoint path."""
        parser = create_parser()
        args = parser.parse_args(["generate", "--checkpoint", "my_cp.json"])

        assert args.checkpoint == "my_cp.json"

    def test_generate_custom_version(self):
        """Test generate command with custom version."""
        parser = create_parser()
        args = parser.parse_args(["generate", "--version", "v2"])

        assert args.version == "v2"

    def test_generate_batch_id(self):
        """Test generate command with batch ID."""
        parser = create_parser()
        args = parser.parse_args(["generate", "--batch-id", "batch_001"])

        assert args.batch_id == "batch_001"

    def test_generate_all_options(self):
        """Test generate command with all options specified."""
        parser = create_parser()
        args = parser.parse_args([
            "generate",
            "--seed", "99",
            "--output", "out.jsonl",
            "--checkpoint", "cp.json",
            "--version", "silver_v3",
            "--batch-id", "b42",
        ])

        assert args.command == "generate"
        assert args.seed == 99
        assert args.output == "out.jsonl"
        assert args.checkpoint == "cp.json"
        assert args.version == "silver_v3"
        assert args.batch_id == "b42"


class TestCreateParserValidate:
    """Tests for the 'validate' command argument parsing."""

    def test_validate_with_input(self):
        """Test validate command parses the required input argument."""
        parser = create_parser()
        args = parser.parse_args(["validate", "silver.jsonl"])

        assert args.command == "validate"
        assert args.input == "silver.jsonl"
        assert args.fixtures_dir is None
        assert args.no_critic is False
        assert args.dedup_threshold == 0.85

    def test_validate_requires_input(self):
        """Test validate command fails without the required input argument."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["validate"])

    def test_validate_fixtures_dir(self):
        """Test validate command with fixtures directory."""
        parser = create_parser()
        args = parser.parse_args(["validate", "data.jsonl", "--fixtures-dir", "/path/to/fixtures"])

        assert args.fixtures_dir == "/path/to/fixtures"

    def test_validate_no_critic_flag(self):
        """Test validate command with --no-critic flag."""
        parser = create_parser()
        args = parser.parse_args(["validate", "data.jsonl", "--no-critic"])

        assert args.no_critic is True

    def test_validate_custom_dedup_threshold(self):
        """Test validate command with custom dedup threshold."""
        parser = create_parser()
        args = parser.parse_args(["validate", "data.jsonl", "--dedup-threshold", "0.90"])

        assert args.dedup_threshold == pytest.approx(0.90)

    def test_validate_all_options(self):
        """Test validate command with all options specified."""
        parser = create_parser()
        args = parser.parse_args([
            "validate", "input.jsonl",
            "--fixtures-dir", "./fix",
            "--no-critic",
            "--dedup-threshold", "0.75",
        ])

        assert args.command == "validate"
        assert args.input == "input.jsonl"
        assert args.fixtures_dir == "./fix"
        assert args.no_critic is True
        assert args.dedup_threshold == pytest.approx(0.75)


class TestCreateParserEvaluate:
    """Tests for the 'evaluate' command argument parsing."""

    def test_evaluate_required_args(self):
        """Test evaluate command with required arguments."""
        parser = create_parser()
        args = parser.parse_args([
            "evaluate", "--version", "silver_v1", "--dataset-dir", "./data"
        ])

        assert args.command == "evaluate"
        assert args.version == "silver_v1"
        assert args.dataset_dir == "./data"
        assert args.output_dir == "./evaluation_output"
        assert args.run_id is None

    def test_evaluate_requires_version(self):
        """Test evaluate command fails without --version."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["evaluate", "--dataset-dir", "./data"])

    def test_evaluate_requires_dataset_dir(self):
        """Test evaluate command fails without --dataset-dir."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["evaluate", "--version", "v1"])

    def test_evaluate_custom_output_dir(self):
        """Test evaluate command with custom output directory."""
        parser = create_parser()
        args = parser.parse_args([
            "evaluate", "--version", "v1", "--dataset-dir", ".", "--output-dir", "/tmp/reports"
        ])

        assert args.output_dir == "/tmp/reports"

    def test_evaluate_run_id(self):
        """Test evaluate command with run ID."""
        parser = create_parser()
        args = parser.parse_args([
            "evaluate", "--version", "v1", "--dataset-dir", ".", "--run-id", "run_123"
        ])

        assert args.run_id == "run_123"

    def test_evaluate_all_options(self):
        """Test evaluate command with all options specified."""
        parser = create_parser()
        args = parser.parse_args([
            "evaluate",
            "--version", "silver_v2",
            "--dataset-dir", "/datasets",
            "--output-dir", "/reports",
            "--run-id", "run_abc",
        ])

        assert args.command == "evaluate"
        assert args.version == "silver_v2"
        assert args.dataset_dir == "/datasets"
        assert args.output_dir == "/reports"
        assert args.run_id == "run_abc"


class TestCommandRequired:
    """Tests that a command is required."""

    def test_no_command_raises_system_exit(self):
        """Test that no command causes SystemExit."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_invalid_command_raises_system_exit(self):
        """Test that an invalid command causes SystemExit."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["invalid_command"])


class TestMainReturnCodes:
    """Tests for main() return codes with valid commands.

    Note: generate/evaluate depend on external services (Ollama, dataset files).
    We test validate with a non-existent file to verify it returns 1.
    """

    def test_main_validate_nonexistent_file(self):
        """Test main() returns 1 for validate with non-existent input."""
        result = main(["validate", "nonexistent_file_xyz.jsonl"])
        assert result == 1

    def test_main_evaluate_nonexistent_dir(self):
        """Test main() returns 1 for evaluate with non-existent dataset dir."""
        result = main([
            "evaluate",
            "--version", "v1",
            "--dataset-dir", "/nonexistent/path/xyz",
        ])
        assert result == 1

    def test_main_validate_returns_zero_for_valid_file(self, tmp_path):
        """Test main() returns 0 for validate with a valid (empty) JSONL file."""
        # Create an empty JSONL file
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        result = main(["validate", str(empty_file), "--no-critic"])
        assert result == 0

    def test_main_no_command_raises_system_exit(self):
        """Test main() with no arguments raises SystemExit."""
        with pytest.raises(SystemExit):
            main([])
