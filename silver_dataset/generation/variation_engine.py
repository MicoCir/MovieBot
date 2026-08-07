"""Variation engine for query diversification.

Generates query variations including typos, code-switching, paraphrasing,
and translation. Typo and code-switching are handled deterministically;
paraphrase and translation are LLM-dependent stubs that return the original
query unchanged (to be replaced with LLM calls during generation).
"""

import random


class VariationEngine:
    """Generates query variations: paraphrase, typo, translation, code-switching."""

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def apply_variation(self, query: str, variation_type: str) -> str:
        """Apply a variation to a query string.

        Args:
            query: The original query text.
            variation_type: One of 'typo', 'code_switch', 'paraphrase', 'translation'.

        Returns:
            The modified query string. For 'paraphrase' and 'translation',
            returns the original query unchanged (requires LLM).
        """
        if variation_type == "typo":
            return self._introduce_typo(query)
        elif variation_type == "code_switch":
            return self._code_switch(query)
        elif variation_type == "paraphrase":
            return query  # paraphrase requires LLM — return unchanged
        elif variation_type == "translation":
            return query  # translation requires LLM — return unchanged
        return query

    def _introduce_typo(self, text: str) -> str:
        """Introduce a realistic typo into the text by swapping two adjacent characters."""
        if len(text) < 5:
            return text
        # Swap two adjacent characters
        idx = self._rng.randint(1, len(text) - 2)
        chars = list(text)
        chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
        return "".join(chars)

    def _code_switch(self, text: str) -> str:
        """Introduce simple code-switching (English/Spanish word substitutions)."""
        substitutions = {
            "movies": "películas",
            "recommend": "recomienda",
            "please": "por favor",
            "show": "muéstrame",
            "good": "buenas",
            "new": "nuevas",
            "the": "las",
        }
        words = text.split()
        for i, word in enumerate(words):
            lower = word.lower()
            if lower in substitutions and self._rng.random() > 0.5:
                words[i] = substitutions[lower]
        return " ".join(words)
