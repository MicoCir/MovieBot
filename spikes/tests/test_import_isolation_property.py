# Feature: source-viability-spikes, Property 10: Import Isolation
"""Property-based tests for import isolation verification.

**Validates: Requirements 6.1, 6.2, 6.3**

Tests that the import isolation checker correctly detects forbidden imports
(moviebot, agents, routing, recommendation) in generated Python source strings,
allows valid imports (stdlib, allowed third-party, spikes), and correctly
identifies only forbidden modules in mixed-import sources.
"""

import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from spikes.tests.test_import_isolation import (
    ALLOWED_THIRD_PARTY,
    FORBIDDEN_MODULES,
    check_imports_for_violations,
    extract_imports_from_source,
)


# --- Strategies ---

# Pick from the set of forbidden modules
forbidden_module_names = st.sampled_from(sorted(FORBIDDEN_MODULES))

# Pick from allowed third-party modules
allowed_third_party_names = st.sampled_from(sorted(ALLOWED_THIRD_PARTY))

# Pick from a subset of stdlib modules known to be present everywhere
stdlib_module_names = st.sampled_from([
    "os", "sys", "json", "pathlib", "hashlib", "re", "ast",
    "typing", "collections", "itertools", "functools", "datetime",
    "math", "io", "tempfile", "copy", "enum", "dataclasses",
])

# The spikes module itself is always allowed
spikes_module = st.just("spikes")

# Combined allowed modules: stdlib + allowed third-party + spikes
allowed_module_names = st.one_of(
    stdlib_module_names,
    allowed_third_party_names,
    spikes_module,
)

# Generate submodule paths like "module.submod.thing"
# Use known safe identifier fragments to avoid Python keywords (e.g. "if", "for")
_safe_identifiers = [
    "core", "utils", "helpers", "models", "base", "api",
    "client", "config", "service", "data", "handler", "manager",
    "dispatcher", "engine", "pipeline", "loader", "parser",
]

submodule_suffix = st.one_of(
    st.just(""),
    st.sampled_from(_safe_identifiers).map(lambda s: f".{s}"),
)

# Import statement styles
import_style = st.sampled_from(["import", "from"])


def _build_import_line(module: str, style: str, suffix: str) -> str:
    """Build a syntactically valid Python import statement."""
    full_module = f"{module}{suffix}" if suffix else module
    if style == "import":
        return f"import {full_module}"
    else:
        # from <module> import <something>
        return f"from {full_module} import something"


# Strategy: generate a source with only forbidden imports
@st.composite
def forbidden_only_sources(draw):
    """Generate Python source strings containing only forbidden imports."""
    num_imports = draw(st.integers(min_value=1, max_value=5))
    lines = []
    modules_used = set()
    for _ in range(num_imports):
        module = draw(forbidden_module_names)
        style = draw(import_style)
        suffix = draw(submodule_suffix)
        lines.append(_build_import_line(module, style, suffix))
        modules_used.add(module)
    return "\n".join(lines) + "\n", modules_used


# Strategy: generate a source with only allowed imports
@st.composite
def allowed_only_sources(draw):
    """Generate Python source strings containing only allowed imports."""
    num_imports = draw(st.integers(min_value=1, max_value=5))
    lines = []
    for _ in range(num_imports):
        module = draw(allowed_module_names)
        style = draw(import_style)
        suffix = draw(submodule_suffix)
        lines.append(_build_import_line(module, style, suffix))
    return "\n".join(lines) + "\n"


# Strategy: generate a source with a mix of forbidden and allowed imports
@st.composite
def mixed_sources(draw):
    """Generate Python source strings with both forbidden and allowed imports."""
    num_forbidden = draw(st.integers(min_value=1, max_value=3))
    num_allowed = draw(st.integers(min_value=1, max_value=3))

    lines = []
    forbidden_used = set()

    for _ in range(num_forbidden):
        module = draw(forbidden_module_names)
        style = draw(import_style)
        suffix = draw(submodule_suffix)
        lines.append(_build_import_line(module, style, suffix))
        forbidden_used.add(module)

    for _ in range(num_allowed):
        module = draw(allowed_module_names)
        style = draw(import_style)
        suffix = draw(submodule_suffix)
        lines.append(_build_import_line(module, style, suffix))

    # Shuffle to mix ordering
    shuffled_indices = draw(
        st.permutations(list(range(len(lines))))
    )
    shuffled_lines = [lines[i] for i in shuffled_indices]

    return "\n".join(shuffled_lines) + "\n", forbidden_used


# --- Property Tests ---


@pytest.mark.property
class TestImportIsolationProperty:
    """Property 10: Import Isolation."""

    @given(data=forbidden_only_sources())
    @settings(max_examples=100)
    def test_forbidden_imports_detected(self, data: tuple[str, set[str]]):
        """Source with forbidden imports produces violations for each forbidden module.

        For any Python source containing imports from forbidden modules,
        the checker SHALL detect all forbidden modules present.
        """
        source, forbidden_modules_used = data
        file_path = Path("test_file.py")

        violations = check_imports_for_violations(source, file_path)
        violated_modules = {v.module for v in violations}

        # All forbidden modules in source must appear in violations
        for module in forbidden_modules_used:
            assert module in violated_modules, (
                f"Expected forbidden module '{module}' to be detected as a violation "
                f"in source:\n{source}"
            )

    @given(source=allowed_only_sources())
    @settings(max_examples=100)
    def test_allowed_imports_produce_no_violations(self, source: str):
        """Source with only allowed imports produces an empty violations list.

        For any Python source containing only stdlib, allowed third-party,
        or intra-spikes imports, the checker SHALL return zero violations.
        """
        file_path = Path("test_file.py")

        violations = check_imports_for_violations(source, file_path)

        assert violations == [], (
            f"Expected no violations for allowed-only source, "
            f"but got {violations} for source:\n{source}"
        )

    @given(data=mixed_sources())
    @settings(max_examples=100)
    def test_mixed_imports_only_flag_forbidden(self, data: tuple[str, set[str]]):
        """Source with mixed imports produces violations only for forbidden modules.

        For any Python source containing both forbidden and allowed imports,
        the checker SHALL produce violations only for the forbidden modules,
        not for the allowed ones.
        """
        source, forbidden_modules_used = data
        file_path = Path("test_file.py")

        violations = check_imports_for_violations(source, file_path)
        violated_modules = {v.module for v in violations}

        # All forbidden modules must be detected
        for module in forbidden_modules_used:
            assert module in violated_modules, (
                f"Expected forbidden module '{module}' in violations "
                f"for mixed source:\n{source}"
            )

        # No allowed module should appear in violations
        allowed_set = (
            ALLOWED_THIRD_PARTY
            | {"spikes"}
            | set(sys.stdlib_module_names)
        )
        for v in violations:
            assert v.module not in allowed_set, (
                f"Allowed module '{v.module}' should not be flagged as violation "
                f"in source:\n{source}"
            )
