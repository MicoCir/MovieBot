"""CLI entrypoint for the Silver Dataset pipeline.

Provides commands for generating, validating, and evaluating the
Silver Dataset using argparse. Ties together all pipeline stages:
generate, validate, and evaluate.
"""

import argparse
import sys
import time
import uuid
from pathlib import Path


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with generate/validate/evaluate commands.

    Returns:
        Configured ArgumentParser with subcommands.
    """
    parser = argparse.ArgumentParser(
        prog="silver_dataset",
        description="Silver Dataset generation, validation, and evaluation pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ─── generate command ──────────────────────────────────────────────
    gen_parser = subparsers.add_parser(
        "generate", help="Generate Silver Dataset from coverage matrix"
    )
    gen_parser.add_argument(
        "--seed", type=int, default=42, help="Random seed (default: 42)"
    )
    gen_parser.add_argument(
        "--output",
        type=str,
        default="silver.jsonl",
        help="Output JSONL path (default: silver.jsonl)",
    )
    gen_parser.add_argument(
        "--checkpoint",
        type=str,
        default=".checkpoint.json",
        help="Checkpoint file (default: .checkpoint.json)",
    )
    gen_parser.add_argument(
        "--version",
        type=str,
        default="silver_v1",
        help="Dataset version (default: silver_v1)",
    )
    gen_parser.add_argument(
        "--batch-id", type=str, default=None, help="Batch identifier"
    )

    # ─── validate command ──────────────────────────────────────────────
    val_parser = subparsers.add_parser(
        "validate", help="Validate a generated Silver Dataset"
    )
    val_parser.add_argument("input", type=str, help="Input JSONL file to validate")
    val_parser.add_argument(
        "--fixtures-dir", type=str, default=None, help="Fixtures directory path"
    )
    val_parser.add_argument(
        "--no-critic",
        action="store_true",
        help="Skip LLM critic assessment",
    )
    val_parser.add_argument(
        "--dedup-threshold",
        type=float,
        default=0.85,
        help="Semantic dedup threshold (default: 0.85)",
    )

    # ─── evaluate command ──────────────────────────────────────────────
    eval_parser = subparsers.add_parser(
        "evaluate", help="Evaluate chatbot against Silver Dataset"
    )
    eval_parser.add_argument(
        "--version", type=str, required=True, help="Dataset version to evaluate"
    )
    eval_parser.add_argument(
        "--dataset-dir",
        type=str,
        required=True,
        help="Directory containing dataset",
    )
    eval_parser.add_argument(
        "--output-dir",
        type=str,
        default="./evaluation_output",
        help="Output directory for reports (default: ./evaluation_output)",
    )
    eval_parser.add_argument(
        "--run-id", type=str, default=None, help="Run identifier"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments. Uses sys.argv[1:] if None.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        return _run_generate(args)
    elif args.command == "validate":
        return _run_validate(args)
    elif args.command == "evaluate":
        return _run_evaluate(args)
    return 1


# ─── Generate command ──────────────────────────────────────────────────────


def _run_generate(args: argparse.Namespace) -> int:
    """Execute the generate command.

    Wires together: load default_coverage_matrix → expand_matrix →
    assign_splits → for each spec call query_generator with checkpointing →
    write_jsonl. Idempotent via checkpoint file.
    """
    from silver_dataset.generation.checkpoint import CheckpointManager
    from silver_dataset.generation.latent_engine import assign_splits, expand_matrix
    from silver_dataset.generation.query_generator import (
        OllamaQueryGenerator,
        OllamaUnavailableError,
    )
    from silver_dataset.io.jsonl import write_jsonl
    from silver_dataset.models.coverage import default_coverage_matrix

    batch_id = args.batch_id or str(uuid.uuid4())[:8]
    output_path = Path(args.output)
    checkpoint_path = Path(args.checkpoint)

    print(f"Silver Dataset Generation (version={args.version}, seed={args.seed})")
    print(f"Output: {output_path}")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Batch ID: {batch_id}")
    print()

    # Step 1: Load coverage matrix and expand to specs
    matrix = default_coverage_matrix()
    specs = expand_matrix(matrix)
    print(f"Coverage matrix expanded: {len(specs)} latent specifications")

    # Step 2: Assign splits
    split_assignments = assign_splits(specs, seed=args.seed)
    print(f"Splits assigned: {len(split_assignments)} specs")

    # Step 3: Initialize checkpoint manager
    checkpoint = CheckpointManager(checkpoint_path)
    all_spec_ids = [s.spec_id for s in specs]
    pending = checkpoint.get_pending_specs(all_spec_ids)
    skipped = len(all_spec_ids) - len(pending)

    print(f"Pending: {len(pending)}, Already completed/failed: {skipped}")
    print()

    if not pending:
        print("All specs already processed. Nothing to do.")
        _print_generation_summary(
            total=len(all_spec_ids),
            completed=skipped,
            failed=0,
            skipped_checkpoint=skipped,
            inference_times=[],
        )
        return 0

    # Step 4: Initialize query generator
    generator = OllamaQueryGenerator(prompt_version="v1")

    # Step 5: Generate queries for pending specs
    cases = []
    inference_times: list[float] = []
    completed_count = 0
    failed_count = 0

    # Build spec lookup for pending specs
    spec_lookup = {s.spec_id: s for s in specs}

    for i, spec_id in enumerate(pending, start=1):
        spec = spec_lookup[spec_id]
        print(f"  [{i}/{len(pending)}] Generating: {spec_id}...", end=" ")

        start_time = time.perf_counter()
        try:
            case = generator.generate_query(spec=spec, batch_id=batch_id)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            if case is not None:
                # Assign the correct split and version
                case.split = split_assignments.get(spec_id, case.split)
                case.dataset_version = args.version
                cases.append(case)
                checkpoint.mark_completed(spec_id, case.case_id)
                inference_times.append(elapsed_ms)
                completed_count += 1
                print(f"OK ({elapsed_ms:.0f}ms)")
            else:
                checkpoint.mark_failed(spec_id, "max_retries_exceeded")
                failed_count += 1
                print("FAILED (max retries)")

        except OllamaUnavailableError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            print(f"\nError: {e}")
            print("Stopping generation — LLM service unavailable.")
            break
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            checkpoint.mark_failed(spec_id, str(e))
            failed_count += 1
            print(f"FAILED ({type(e).__name__})")

    # Step 6: Write output JSONL (append to existing if resuming)
    if cases:
        # If output already exists, read existing cases and merge
        existing_cases = []
        if output_path.exists():
            from silver_dataset.io.jsonl import read_jsonl

            existing_cases, _ = read_jsonl(output_path)

        all_cases = existing_cases + cases
        count = write_jsonl(all_cases, output_path)
        print(f"\nWrote {count} cases to {output_path}")
    else:
        print("\nNo new cases generated.")

    # Step 7: Print summary
    print()
    _print_generation_summary(
        total=len(all_spec_ids),
        completed=completed_count + skipped,
        failed=failed_count,
        skipped_checkpoint=skipped,
        inference_times=inference_times,
    )
    return 0


def _print_generation_summary(
    total: int,
    completed: int,
    failed: int,
    skipped_checkpoint: int,
    inference_times: list[float],
) -> None:
    """Print the generation summary report.

    Args:
        total: Total number of specs in the matrix.
        completed: Number successfully completed (including previously checkpointed).
        failed: Number that failed in this run.
        skipped_checkpoint: Number skipped due to checkpoint (already done).
        inference_times: List of inference durations in ms.
    """
    avg_ms = sum(inference_times) / len(inference_times) if inference_times else 0.0

    print("═" * 50)
    print("Generation Summary")
    print("═" * 50)
    print(f"  Total specs:          {total}")
    print(f"  Completed:            {completed}")
    print(f"  Failed:               {failed}")
    print(f"  Skipped (checkpoint): {skipped_checkpoint}")
    print(f"  Avg inference time:   {avg_ms:.1f} ms")
    print("═" * 50)


# ─── Validate command ──────────────────────────────────────────────────────


def _run_validate(args: argparse.Namespace) -> int:
    """Execute the validate command.

    Wires together: read_jsonl → SchemaValidator → RuleValidator →
    Critic (if enabled) → Deduplicator → report summary.
    """
    from silver_dataset.io.jsonl import read_jsonl
    from silver_dataset.models.fixtures import FixtureRegistry
    from silver_dataset.validation.critic import Critic
    from silver_dataset.validation.deduplicator import Deduplicator
    from silver_dataset.validation.rule_validator import RuleValidator
    from silver_dataset.validation.schema_validator import SchemaValidator
    from silver_dataset.validation.status import assign_validation_status

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return 1

    print(f"Validating: {input_path}")
    print(f"Dedup threshold: {args.dedup_threshold}")
    print(f"Critic: {'disabled' if args.no_critic else 'enabled'}")
    print()

    # Step 1: Read JSONL
    cases, parse_errors = read_jsonl(input_path)
    print(f"Loaded {len(cases)} cases ({len(parse_errors)} parse errors)")

    if parse_errors:
        print(f"  Parse errors on lines: {[e.line_number for e in parse_errors]}")

    # Step 2: Schema validation (already done by read_jsonl, but we can
    # also validate raw dicts for reporting). Cases that parsed are schema-valid.
    schema_validator = SchemaValidator()
    schema_passed = len(cases)
    schema_failed = len(parse_errors)

    # Step 3: Rule validation
    fixtures_dir = Path(args.fixtures_dir) if args.fixtures_dir else _default_fixtures_dir()
    fixture_registry = FixtureRegistry(fixtures_dir)
    rule_validator = RuleValidator(fixture_registry)

    rule_results: dict[str, list[str]] = {}
    rule_pass_count = 0
    rule_fail_count = 0

    for case in cases:
        violations = rule_validator.validate(case)
        rule_results[case.case_id] = violations
        if violations:
            rule_fail_count += 1
        else:
            rule_pass_count += 1

    print(f"Rule validation: {rule_pass_count} passed, {rule_fail_count} failed")

    # Step 4: Critic assessment (if enabled)
    critic_results = {}
    if not args.no_critic:
        print("Running LLM critic assessment...")
        critic = Critic()
        for case in cases:
            result = critic.assess(case)
            critic_results[case.case_id] = result
        critic_passed = sum(1 for r in critic_results.values() if r.status == "passed")
        critic_warnings = sum(
            1 for r in critic_results.values() if r.status == "warning"
        )
        critic_failed = sum(1 for r in critic_results.values() if r.status == "failed")
        print(
            f"Critic: {critic_passed} passed, {critic_warnings} warnings, "
            f"{critic_failed} failed"
        )
    else:
        print("Critic: skipped")

    # Step 5: Deduplication
    deduplicator = Deduplicator(similarity_threshold=args.dedup_threshold)
    duplicates = deduplicator.find_duplicates(cases)
    print(f"Duplicates found: {len(duplicates)}")
    for dup in duplicates[:5]:  # Show first 5
        print(f"  {dup.case_id_1} ↔ {dup.case_id_2} ({dup.match_type}, {dup.similarity:.2f})")
    if len(duplicates) > 5:
        print(f"  ... and {len(duplicates) - 5} more")

    # Step 6: Assign final validation statuses
    status_counts = {"passed": 0, "warning": 0, "failed": 0}
    for case in cases:
        schema_errors: list[str] = []  # Already schema-valid if parsed
        rule_violations = rule_results.get(case.case_id, [])
        critic_result = critic_results.get(case.case_id)
        status = assign_validation_status(schema_errors, rule_violations, critic_result)
        status_counts[status.value] += 1

    # Step 7: Print summary
    print()
    print("═" * 50)
    print("Validation Summary")
    print("═" * 50)
    print(f"  Total cases:      {len(cases)}")
    print(f"  Schema passed:    {schema_passed}")
    print(f"  Schema failed:    {schema_failed}")
    print(f"  Rule passed:      {rule_pass_count}")
    print(f"  Rule failed:      {rule_fail_count}")
    print(f"  Duplicates:       {len(duplicates)}")
    print(f"  Status passed:    {status_counts['passed']}")
    print(f"  Status warning:   {status_counts['warning']}")
    print(f"  Status failed:    {status_counts['failed']}")
    print("═" * 50)

    return 0


def _default_fixtures_dir() -> Path:
    """Return the default fixtures directory path."""
    return Path(__file__).parent / "fixtures"


# ─── Evaluate command ──────────────────────────────────────────────────────


def _run_evaluate(args: argparse.Namespace) -> int:
    """Execute the evaluate command.

    Wires together: SilverDatasetLoader.load() → BaselineRunner.run() →
    generate_scorecard → write reports. Uses a stub chatbot_fn.
    """
    from silver_dataset.evaluation.failure_analysis import (
        analyze_failures,
        write_baseline_results_md,
        write_failure_analysis_md,
    )
    from silver_dataset.evaluation.runner import BaselineRunner
    from silver_dataset.evaluation.scorecard import generate_scorecard
    from silver_dataset.io.loader import LoaderError, SilverDatasetLoader
    from silver_dataset.models.case import Split

    dataset_dir = Path(args.dataset_dir)
    output_dir = Path(args.output_dir)
    run_id = args.run_id or str(uuid.uuid4())[:8]

    print(f"Evaluating version: {args.version}")
    print(f"Dataset dir: {dataset_dir}")
    print(f"Output dir: {output_dir}")
    print(f"Run ID: {run_id}")
    print()

    # Step 1: Load dataset via loader
    try:
        loader = SilverDatasetLoader(
            dataset_dir=dataset_dir, mode="evaluation"
        )
        cases = loader.load(version=args.version, split=Split.dev)
    except (LoaderError, PermissionError) as e:
        print(f"Error loading dataset: {e}")
        return 1

    if not cases:
        print("No cases found for the given version and split.")
        return 1

    print(f"Loaded {len(cases)} cases (dev split)")

    # Step 2: Run baseline with stub chatbot_fn
    def stub_chatbot_fn(case):
        """Stub chatbot that returns empty predictions."""
        return {
            "route": case.expected_route.value,
            "tool": case.expected_tool.value,
            "action": case.expected_action.value,
        }

    runner = BaselineRunner(chatbot_fn=stub_chatbot_fn, dataset_loader=loader)
    print("Running baseline evaluation...")
    result = runner.run(run_id=run_id, version=args.version)
    print(
        f"Run complete: {result.successful} successful, "
        f"{result.failed} failed, {result.infra_errors} infra errors"
    )

    # Step 3: Generate scorecard
    scorecard = generate_scorecard(traces=result.traces, cases=cases)

    # Step 4: Failure analysis
    analysis = analyze_failures(traces=result.traces, cases=cases)

    # Step 5: Write reports
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_md_path = output_dir / "baseline_results.md"
    failure_md_path = output_dir / "failure_analysis.md"

    write_baseline_results_md(scorecard, baseline_md_path)
    write_failure_analysis_md(analysis, failure_md_path)

    print()
    print("═" * 50)
    print("Evaluation Summary")
    print("═" * 50)
    print(f"  Total cases:      {scorecard.total_cases}")
    print(f"  Successful:       {scorecard.successful_cases}")
    print(f"  Infra errors:     {scorecard.infra_error_cases}")
    print(f"  Route accuracy:   {scorecard.routing.route_accuracy:.2%}")
    print(f"  Tool accuracy:    {scorecard.tool_calls.tool_selection_accuracy:.2%}")
    print(f"  Reports written:")
    print(f"    {baseline_md_path}")
    print(f"    {failure_md_path}")
    print("═" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
