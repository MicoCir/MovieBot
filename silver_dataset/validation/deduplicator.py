"""Deduplication detection for Silver Dataset cases.

Detects duplicate cases using three matching strategies:
- Exact: queries are identical strings
- Normalized: case-insensitive with stripped extra punctuation/whitespace
- Semantic: (stub) comparing normalized queries with similarity threshold
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from silver_dataset.models.case import SilverCase


@dataclass
class DuplicatePair:
    """A detected duplicate pair between two cases.

    Attributes:
        case_id_1: First case ID in the duplicate pair.
        case_id_2: Second case ID in the duplicate pair.
        match_type: Type of match — "exact", "normalized", or "semantic".
        similarity: Similarity score (1.0 for exact/normalized, configurable for semantic).
    """

    case_id_1: str
    case_id_2: str
    match_type: str  # "exact", "normalized", "semantic"
    similarity: float


class Deduplicator:
    """Detects duplicate cases within the Silver Dataset.

    Detection strategies:
    1. Exact: queries are identical strings.
    2. Normalized: case-insensitive comparison with extra punctuation
       and whitespace stripped.
    3. Semantic: comparing normalized queries — flags pairs whose
       character-level similarity exceeds a configurable threshold.
       Uses a simple ratio-based similarity as a stub for future
       embedding-based approaches.
    """

    def __init__(self, similarity_threshold: float = 0.85) -> None:
        """Initialize the deduplicator.

        Args:
            similarity_threshold: Minimum similarity score (0.0–1.0)
                for semantic duplicate detection. Default 0.85.
        """
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0.0 and 1.0")
        self._threshold = similarity_threshold

    def find_duplicates(self, cases: list[SilverCase]) -> list[DuplicatePair]:
        """Find all duplicate pairs within the given cases.

        Checks all pairs for exact, normalized, and semantic matches.
        A pair is reported at most once with the strongest match type
        (exact > normalized > semantic).

        Args:
            cases: List of validated SilverCase instances to check.

        Returns:
            List of DuplicatePair instances for all detected duplicates.
        """
        duplicates: list[DuplicatePair] = []
        n = len(cases)

        # Pre-compute normalized queries for efficiency
        normalized = [self._normalize(case.query) for case in cases]

        for i in range(n):
            for j in range(i + 1, n):
                pair = self._compare(cases[i], cases[j], normalized[i], normalized[j])
                if pair is not None:
                    duplicates.append(pair)

        return duplicates

    def _compare(
        self,
        case_a: SilverCase,
        case_b: SilverCase,
        norm_a: str,
        norm_b: str,
    ) -> DuplicatePair | None:
        """Compare two cases and return a DuplicatePair if they match."""
        # Exact match
        if case_a.query == case_b.query:
            return DuplicatePair(
                case_id_1=case_a.case_id,
                case_id_2=case_b.case_id,
                match_type="exact",
                similarity=1.0,
            )

        # Normalized match
        if norm_a == norm_b:
            return DuplicatePair(
                case_id_1=case_a.case_id,
                case_id_2=case_b.case_id,
                match_type="normalized",
                similarity=1.0,
            )

        # Semantic match (character-level similarity stub)
        similarity = self._compute_similarity(norm_a, norm_b)
        if similarity >= self._threshold:
            return DuplicatePair(
                case_id_1=case_a.case_id,
                case_id_2=case_b.case_id,
                match_type="semantic",
                similarity=similarity,
            )

        return None

    @staticmethod
    def _normalize(query: str) -> str:
        """Normalize a query for comparison.

        Normalization steps:
        1. Unicode NFKC normalization
        2. Convert to lowercase
        3. Strip leading/trailing whitespace
        4. Collapse multiple whitespace to single space
        5. Remove non-alphanumeric characters except spaces
        """
        text = unicodedata.normalize("NFKC", query)
        text = text.casefold().strip()
        # Remove non-alphanumeric except spaces
        text = re.sub(r"[^\w\s]", "", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _compute_similarity(a: str, b: str) -> float:
        """Compute character-level similarity using SequenceMatcher ratio.

        This is a simple stub for future embedding-based semantic similarity.
        Uses Python's difflib SequenceMatcher for character-level comparison.

        Args:
            a: First normalized string.
            b: Second normalized string.

        Returns:
            Similarity ratio between 0.0 and 1.0.
        """
        from difflib import SequenceMatcher

        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()
