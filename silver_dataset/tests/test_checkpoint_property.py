"""Property-based tests for the CheckpointManager.

Feature: silver-dataset-generation
Property tested:
- Property 9: Checkpoint resumption without duplicates

For any interrupted generation state (partial checkpoint), resuming generation
SHALL not produce any case_id that already exists in the checkpoint, and all
pending specifications SHALL be attempted.
"""

import pathlib
import tempfile

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from silver_dataset.generation.checkpoint import CheckpointManager


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

spec_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "Nd"), whitelist_characters="-_"),
    min_size=1,
    max_size=30,
)

spec_id_list_strategy = st.lists(
    spec_id_strategy,
    min_size=1,
    max_size=20,
    unique=True,
)


# ---------------------------------------------------------------------------
# Property 9: Checkpoint resumption without duplicates
# **Validates: Requirement 4.4**
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(
    all_specs=spec_id_list_strategy,
    data=st.data(),
)
@settings(max_examples=100)
def test_get_pending_specs_excludes_completed_and_failed(
    all_specs: list[str],
    data: st.DataObject,
):
    """For any interrupted generation state, get_pending_specs SHALL return only
    specs that are NOT in the completed or failed sets."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        checkpoint_path = pathlib.Path(tmp_dir) / "checkpoint.json"
        mgr = CheckpointManager(checkpoint_path)

        # Mark a subset as completed
        n = len(all_specs)
        num_completed = data.draw(st.integers(min_value=0, max_value=n // 2))
        completed_specs = all_specs[:num_completed]
        for spec_id in completed_specs:
            mgr.mark_completed(spec_id, f"case_{spec_id}")

        # Mark a different subset as failed
        remaining_after_completed = all_specs[num_completed:]
        num_failed = data.draw(
            st.integers(min_value=0, max_value=len(remaining_after_completed) // 2)
        )
        failed_specs = remaining_after_completed[:num_failed]
        for spec_id in failed_specs:
            mgr.mark_failed(spec_id, "test error")

        # Get pending
        pending = mgr.get_pending_specs(all_specs)

        # Pending must not contain any completed or failed specs
        completed_set = set(completed_specs)
        failed_set = set(failed_specs)
        for spec_id in pending:
            assert spec_id not in completed_set, (
                f"Pending spec '{spec_id}' is already completed"
            )
            assert spec_id not in failed_set, (
                f"Pending spec '{spec_id}' is already failed"
            )

        # All non-done specs must be in pending
        done_set = completed_set | failed_set
        expected_pending = [s for s in all_specs if s not in done_set]
        assert pending == expected_pending


@pytest.mark.property
@given(
    all_specs=spec_id_list_strategy,
    data=st.data(),
)
@settings(max_examples=100)
def test_marking_completed_does_not_create_duplicates(
    all_specs: list[str],
    data: st.DataObject,
):
    """Marking a spec as completed SHALL not produce duplicates in subsequent
    get_pending_specs calls — the spec disappears exactly once."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        checkpoint_path = pathlib.Path(tmp_dir) / "checkpoint.json"
        mgr = CheckpointManager(checkpoint_path)

        # Mark first N specs completed
        n = data.draw(st.integers(min_value=1, max_value=len(all_specs)))
        for spec_id in all_specs[:n]:
            mgr.mark_completed(spec_id, f"case_{spec_id}")

        # Call get_pending_specs multiple times — should always be the same result
        pending_1 = mgr.get_pending_specs(all_specs)
        pending_2 = mgr.get_pending_specs(all_specs)

        assert pending_1 == pending_2
        assert len(pending_1) == len(all_specs) - n

        # No duplicates in the pending list
        assert len(pending_1) == len(set(pending_1))


@pytest.mark.property
@given(all_specs=spec_id_list_strategy)
@settings(max_examples=100)
def test_checkpoint_resumption_preserves_all_case_ids(
    all_specs: list[str],
):
    """After marking specs completed and reloading the checkpoint from disk,
    all previously completed case_ids SHALL be preserved and pending specs
    SHALL NOT overlap with completed ones."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        checkpoint_path = pathlib.Path(tmp_dir) / "checkpoint.json"
        mgr = CheckpointManager(checkpoint_path)

        # Mark half as completed
        half = len(all_specs) // 2
        completed_case_ids = set()
        for spec_id in all_specs[:half]:
            case_id = f"case_{spec_id}"
            mgr.mark_completed(spec_id, case_id)
            completed_case_ids.add(case_id)

        # Simulate restart: create a new manager from the same file
        mgr2 = CheckpointManager(checkpoint_path)

        # Verify state is preserved
        pending = mgr2.get_pending_specs(all_specs)
        for spec_id in all_specs[:half]:
            assert mgr2.is_completed(spec_id)
            assert spec_id not in pending

        # Pending specs are exactly the second half
        assert set(pending) == set(all_specs[half:])

        # No overlap between completed spec_ids and pending spec_ids
        completed_spec_set = set(all_specs[:half])
        assert completed_spec_set.isdisjoint(set(pending))
