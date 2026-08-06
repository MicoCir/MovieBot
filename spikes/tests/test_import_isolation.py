"""Import isolation checker for spikes directory.

Validates Requirements 6.1, 6.2, 6.3:
- TMDB spike executes without importing agent/routing/recommendation modules
- Netflix spike executes without importing agent/routing/recommendation modules
- Meilisearch spike executes without importing agent/routing/recommendation modules
"""

import ast
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SPIKES_ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_MODULES = frozenset({
    "moviebot",
    "agents",
    "routing",
    "recommendation",
})

ALLOWED_THIRD_PARTY = frozenset({
    "httpx",
    "pydantic",
    "pandas",
    "hypothesis",
    "docker",
    "respx",
    "pytest",
    "kaggle",
})

# ---------------------------------------------------------------------------
# Reusable checker logic
# ---------------------------------------------------------------------------


class ImportViolation(NamedTuple):
    """Represents a forbidden import found in a source file."""

    file: Path
    line: int
    module: str
    reason: str


def extract_imports_from_source(source: str) -> list[str]:
    """Parse Python source code and return all top-level imported module names.

    Returns the root module name for each import statement found.
    For example, `from foo.bar import baz` returns 'foo'.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                modules.append(root)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                modules.append(root)
    return modules


def _is_stdlib_module(module_name: str) -> bool:
    """Check if a module name belongs to the Python standard library."""
    if module_name in sys.stdlib_module_names:
        return True
    # Also check for common stdlib modules that might not be in the frozen set
    # on all platforms
    stdlib_extras = {"_thread", "__future__", "typing_extensions"}
    return module_name in stdlib_extras


def check_imports_for_violations(
    source: str,
    file_path: Path | None = None,
) -> list[ImportViolation]:
    """Check a Python source string for forbidden imports.

    This function is the core reusable checker. It:
    1. Parses import statements from the source
    2. Checks each import against the forbidden module list
    3. Checks that non-stdlib, non-spikes imports are in the allowed third-party set

    Args:
        source: Python source code as a string.
        file_path: Optional file path for error reporting.

    Returns:
        List of ImportViolation instances. Empty means the source is compliant.
    """
    violations: list[ImportViolation] = []
    file_ref = file_path or Path("<unknown>")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                line = node.lineno
                violation = _check_module(root, file_ref, line)
                if violation:
                    violations.append(violation)

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                line = node.lineno
                violation = _check_module(root, file_ref, line)
                if violation:
                    violations.append(violation)

    return violations


def _check_module(
    module_name: str,
    file_path: Path,
    line: int,
) -> ImportViolation | None:
    """Check a single module name against forbidden and allowed lists."""
    # Forbidden modules — always a violation
    if module_name in FORBIDDEN_MODULES:
        return ImportViolation(
            file=file_path,
            line=line,
            module=module_name,
            reason=f"Forbidden module: '{module_name}' belongs to moviebot core/agents/routing/recommendation",
        )

    # Allowed categories (no violation)
    if _is_stdlib_module(module_name):
        return None
    if module_name in ALLOWED_THIRD_PARTY:
        return None
    if module_name == "spikes":
        return None

    # Unknown module — potential violation (not stdlib, not allowed third-party, not spikes)
    return ImportViolation(
        file=file_path,
        line=line,
        module=module_name,
        reason=f"Unknown module: '{module_name}' is not stdlib, not an allowed third-party package, and not intra-spikes",
    )


def scan_spikes_directory(spikes_root: Path | None = None) -> list[ImportViolation]:
    """Scan all .py files under the spikes directory for import violations.

    Args:
        spikes_root: Root of the spikes directory. Defaults to the project's spikes/ dir.

    Returns:
        List of all ImportViolation instances found across all files.
    """
    root = spikes_root or SPIKES_ROOT
    all_violations: list[ImportViolation] = []

    for py_file in sorted(root.rglob("*.py")):
        # Skip __pycache__ directories
        if "__pycache__" in str(py_file):
            continue

        source = py_file.read_text(encoding="utf-8")
        violations = check_imports_for_violations(source, py_file)
        all_violations.extend(violations)

    return all_violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImportIsolation:
    """Verify that spikes directory has no forbidden imports."""

    def test_no_forbidden_imports_in_spikes(self):
        """All .py files under spikes/ must have zero references to forbidden modules.

        Validates: Requirements 6.1, 6.2, 6.3
        """
        violations = scan_spikes_directory()

        # Filter to only forbidden module violations (not unknown third-party)
        forbidden_violations = [
            v for v in violations if v.module in FORBIDDEN_MODULES
        ]

        if forbidden_violations:
            report = "\n".join(
                f"  {v.file}:{v.line} -> import '{v.module}' ({v.reason})"
                for v in forbidden_violations
            )
            pytest.fail(
                f"Found {len(forbidden_violations)} forbidden import(s) in spikes/:\n{report}"
            )

    def test_only_allowed_dependencies(self):
        """All imports must be stdlib, allowed third-party, or intra-spikes.

        Validates: Requirements 6.1, 6.2, 6.3
        """
        violations = scan_spikes_directory()

        if violations:
            report = "\n".join(
                f"  {v.file}:{v.line} -> import '{v.module}' ({v.reason})"
                for v in violations
            )
            pytest.fail(
                f"Found {len(violations)} import violation(s) in spikes/:\n{report}"
            )

    def test_tmdb_spike_isolation(self):
        """TMDB spike files have no forbidden imports.

        Validates: Requirement 6.1
        """
        tmdb_dir = SPIKES_ROOT / "tmdb"
        violations = scan_spikes_directory(tmdb_dir)
        forbidden_violations = [
            v for v in violations if v.module in FORBIDDEN_MODULES
        ]

        if forbidden_violations:
            report = "\n".join(
                f"  {v.file}:{v.line} -> import '{v.module}'"
                for v in forbidden_violations
            )
            pytest.fail(
                f"TMDB spike has forbidden imports:\n{report}"
            )

    def test_netflix_spike_isolation(self):
        """Netflix spike files have no forbidden imports.

        Validates: Requirement 6.2
        """
        netflix_dir = SPIKES_ROOT / "netflix"
        violations = scan_spikes_directory(netflix_dir)
        forbidden_violations = [
            v for v in violations if v.module in FORBIDDEN_MODULES
        ]

        if forbidden_violations:
            report = "\n".join(
                f"  {v.file}:{v.line} -> import '{v.module}'"
                for v in forbidden_violations
            )
            pytest.fail(
                f"Netflix spike has forbidden imports:\n{report}"
            )

    def test_meilisearch_spike_isolation(self):
        """Meilisearch spike files have no forbidden imports.

        Validates: Requirement 6.3
        """
        meilisearch_dir = SPIKES_ROOT / "meilisearch"
        violations = scan_spikes_directory(meilisearch_dir)
        forbidden_violations = [
            v for v in violations if v.module in FORBIDDEN_MODULES
        ]

        if forbidden_violations:
            report = "\n".join(
                f"  {v.file}:{v.line} -> import '{v.module}'"
                for v in forbidden_violations
            )
            pytest.fail(
                f"Meilisearch spike has forbidden imports:\n{report}"
            )


@pytest.mark.unit
class TestCheckerFunction:
    """Unit tests for the reusable checker function itself."""

    def test_detects_forbidden_import(self):
        """Checker detects a direct forbidden import."""
        source = "import moviebot\n"
        violations = check_imports_for_violations(source)
        assert len(violations) == 1
        assert violations[0].module == "moviebot"

    def test_detects_forbidden_from_import(self):
        """Checker detects a from-style forbidden import."""
        source = "from agents.core import Agent\n"
        violations = check_imports_for_violations(source)
        assert len(violations) == 1
        assert violations[0].module == "agents"

    def test_detects_forbidden_routing_import(self):
        """Checker detects routing module import."""
        source = "from routing.dispatcher import route\n"
        violations = check_imports_for_violations(source)
        assert len(violations) == 1
        assert violations[0].module == "routing"

    def test_detects_forbidden_recommendation_import(self):
        """Checker detects recommendation module import."""
        source = "import recommendation\n"
        violations = check_imports_for_violations(source)
        assert len(violations) == 1
        assert violations[0].module == "recommendation"

    def test_allows_stdlib_imports(self):
        """Standard library imports produce no violations."""
        source = "import os\nimport sys\nfrom pathlib import Path\nimport json\n"
        violations = check_imports_for_violations(source)
        assert violations == []

    def test_allows_third_party_imports(self):
        """Allowed third-party imports produce no violations."""
        source = "import httpx\nimport pydantic\nimport pandas\nfrom hypothesis import given\nimport docker\n"
        violations = check_imports_for_violations(source)
        assert violations == []

    def test_allows_intra_spikes_imports(self):
        """Imports from the spikes namespace are allowed."""
        source = "from spikes.common.fingerprint import compute_sha256\nfrom spikes.tmdb.validators import validate_tmdb_url\n"
        violations = check_imports_for_violations(source)
        assert violations == []

    def test_detects_multiple_violations(self):
        """Checker finds all violations in a file with multiple forbidden imports."""
        source = "import moviebot\nfrom agents import foo\nimport os\n"
        violations = check_imports_for_violations(source)
        assert len(violations) == 2
        modules = {v.module for v in violations}
        assert modules == {"moviebot", "agents"}

    def test_empty_source(self):
        """Empty source produces no violations."""
        violations = check_imports_for_violations("")
        assert violations == []

    def test_syntax_error_source(self):
        """Source with syntax errors produces no violations (gracefully handled)."""
        source = "def broken(\n"
        violations = check_imports_for_violations(source)
        assert violations == []

    def test_allows_pytest_import(self):
        """Pytest is an allowed third-party import."""
        source = "import pytest\nfrom pytest import fixture\n"
        violations = check_imports_for_violations(source)
        assert violations == []

    def test_allows_respx_import(self):
        """respx is an allowed third-party import."""
        source = "import respx\n"
        violations = check_imports_for_violations(source)
        assert violations == []

    def test_allows_kaggle_import(self):
        """kaggle is an allowed third-party import."""
        source = "import kaggle\nfrom kaggle.api import KaggleApi\n"
        violations = check_imports_for_violations(source)
        assert violations == []
