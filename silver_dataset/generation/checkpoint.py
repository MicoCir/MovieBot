"""Checkpoint manager for resumable dataset generation.

Tracks which specifications have been successfully generated or have failed,
enabling the generation pipeline to resume without duplicating work.
"""

from pathlib import Path
import json
from collections import Counter


class CheckpointManager:
    """Tracks generation progress for resumable execution.

    Uses a JSON file to persist state. Supports marking specs as completed
    or failed, and retrieving pending specs for resumption.
    """

    def __init__(self, checkpoint_path: Path):
        self._path = checkpoint_path
        self._state: dict = {"completed": {}, "failed": {}}
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                self._state = json.load(f)

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)

    def is_completed(self, spec_id: str) -> bool:
        return spec_id in self._state.get("completed", {})

    def mark_completed(self, spec_id: str, case_id: str) -> None:
        self._state.setdefault("completed", {})[spec_id] = case_id
        self._save()

    def mark_failed(self, spec_id: str, error: str) -> None:
        self._state.setdefault("failed", {})[spec_id] = error
        self._save()

    def get_pending_specs(self, all_specs: list[str]) -> list[str]:
        completed = set(self._state.get("completed", {}).keys())
        failed = set(self._state.get("failed", {}).keys())
        done = completed | failed
        return [s for s in all_specs if s not in done]

    def get_failure_summary(self) -> dict[str, int]:
        """Return count of failures grouped by error message."""
        counter: Counter = Counter()
        for error in self._state.get("failed", {}).values():
            counter[error] += 1
        return dict(counter)
