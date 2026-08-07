"""I/O layer for the Silver Dataset.

Handles JSONL serialization/deserialization with per-line error reporting,
human-readable pretty printing, and filtered dataset loading via the Loader API.
"""

from silver_dataset.io.jsonl import ParseError, read_jsonl, write_jsonl
from silver_dataset.io.loader import LoaderError, SilverDatasetLoader
from silver_dataset.io.pretty_printer import PrettyPrinter

__all__ = [
    "LoaderError",
    "ParseError",
    "PrettyPrinter",
    "SilverDatasetLoader",
    "read_jsonl",
    "write_jsonl",
]
