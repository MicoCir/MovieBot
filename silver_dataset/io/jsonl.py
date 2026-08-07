"""JSONL serialization and deserialization for the Silver Dataset.

Provides write_jsonl and read_jsonl functions for streaming SilverCase
instances to and from JSONL files with per-line error reporting.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from silver_dataset.models.case import SilverCase


@dataclass
class ParseError:
    """Represents a per-line parsing error encountered during JSONL reading.

    Attributes:
        line_number: 1-based line number where the error occurred.
        error: String description of the error.
        raw_content: The raw line content that failed to parse.
    """

    line_number: int
    error: str
    raw_content: str


def write_jsonl(cases: Iterable[SilverCase], path: Path) -> int:
    """Write cases as JSONL. Returns number of cases written.

    Each case is serialized as a single JSON line using Pydantic's
    model_dump_json() to ensure all types are JSON-serializable.

    Args:
        cases: Iterable of SilverCase instances to serialize.
        path: Destination file path. Parent directories must exist.

    Returns:
        Number of cases written. Returns 0 for empty iterables
        (an empty file is still created).
    """
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        for case in cases:
            json_line = case.model_dump_json()
            f.write(json_line + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> tuple[list[SilverCase], list[ParseError]]:
    """Read JSONL file, returning valid cases and per-line errors.

    Each line is independently parsed and validated against the SilverCase model.
    Invalid lines are collected as ParseError instances without interrupting
    the parsing of remaining lines (Requirement 12.4).

    Args:
        path: Path to the JSONL file.

    Returns:
        Tuple of (valid_cases, errors).
    """
    cases: list[SilverCase] = []
    errors: list[ParseError] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                case = SilverCase.model_validate(raw)
                cases.append(case)
            except (json.JSONDecodeError, Exception) as e:
                errors.append(
                    ParseError(
                        line_number=line_num,
                        error=str(e),
                        raw_content=line,
                    )
                )
    return cases, errors
