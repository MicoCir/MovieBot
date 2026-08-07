"""Property-based tests for checksum determinism and sensitivity.

**Validates: Requirement 7.2**

Property 16: Checksum determinism and sensitivity
- For any list of SilverCase instances, compute_dataset_checksum SHALL produce
  the same hash for identical content (determinism).
- For any single-field modification to any case, the checksum SHALL change
  (sensitivity).
"""

import copy
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from silver_dataset.models.case import SilverCase
from silver_dataset.tests.strategies import silver_case_strategy
from silver_dataset.versioning.checksum import (
    compute_dataset_checksum,
    verify_checksum,
)


@pytest.mark.property
@given(cases=st.lists(silver_case_strategy(), min_size=1, max_size=5))
@settings(max_examples=100)
def test_checksum_determinism(cases: list[SilverCase]):
    """Same cases produce the same checksum, regardless of order.

    **Validates: Requirements 7.2**

    Property: compute_dataset_checksum is order-independent and deterministic.
    For any permutation of the input list, the checksum must be identical.
    """
    c1 = compute_dataset_checksum(cases)
    shuffled = cases.copy()
    random.shuffle(shuffled)
    c2 = compute_dataset_checksum(shuffled)
    assert c1 == c2, "Checksum must be identical regardless of input order"


@pytest.mark.property
@given(cases=st.lists(silver_case_strategy(), min_size=1, max_size=5))
@settings(max_examples=100)
def test_checksum_idempotent(cases: list[SilverCase]):
    """Calling compute_dataset_checksum twice on the same input produces identical results.

    **Validates: Requirements 7.2**

    Property: The function is pure — no hidden state affects the output.
    """
    c1 = compute_dataset_checksum(cases)
    c2 = compute_dataset_checksum(cases)
    assert c1 == c2, "Checksum must be idempotent for the same input"


@pytest.mark.property
@given(cases=st.lists(silver_case_strategy(), min_size=1, max_size=5))
@settings(max_examples=100)
def test_checksum_sensitivity(cases: list[SilverCase]):
    """Modifying any field changes the checksum.

    **Validates: Requirements 7.2**

    Property: A single-field modification to any case changes the checksum.
    This ensures the checksum captures all content.
    """
    original_checksum = compute_dataset_checksum(cases)

    # Deep copy and modify the query field of the first case
    modified_cases = copy.deepcopy(cases)
    modified_cases[0].query = modified_cases[0].query + "_modified_xyzzy"

    modified_checksum = compute_dataset_checksum(modified_cases)
    assert original_checksum != modified_checksum, (
        "Checksum must change when any case field is modified"
    )


@pytest.mark.property
@given(cases=st.lists(silver_case_strategy(), min_size=1, max_size=5))
@settings(max_examples=100)
def test_verify_checksum_positive(cases: list[SilverCase]):
    """verify_checksum returns True for a matching checksum.

    **Validates: Requirements 7.2**
    """
    checksum = compute_dataset_checksum(cases)
    assert verify_checksum(cases, checksum) is True


@pytest.mark.property
@given(cases=st.lists(silver_case_strategy(), min_size=1, max_size=5))
@settings(max_examples=100)
def test_verify_checksum_negative(cases: list[SilverCase]):
    """verify_checksum returns False for a non-matching checksum.

    **Validates: Requirements 7.2**
    """
    assert verify_checksum(cases, "0" * 64) is False


@pytest.mark.property
@given(cases=st.lists(silver_case_strategy(), min_size=1, max_size=5))
@settings(max_examples=100)
def test_checksum_is_valid_sha256(cases: list[SilverCase]):
    """compute_dataset_checksum returns a valid 64-character hex string (SHA-256).

    **Validates: Requirements 7.2**
    """
    checksum = compute_dataset_checksum(cases)
    assert len(checksum) == 64, "SHA-256 hex digest must be 64 characters"
    assert all(c in "0123456789abcdef" for c in checksum), (
        "SHA-256 hex digest must contain only hex characters"
    )
