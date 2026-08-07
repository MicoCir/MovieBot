"""Version registry and integrity validation.

Maps version identifiers to checksums and metadata, enabling the loader
to validate dataset integrity before serving cases.
"""

from pydantic import BaseModel


class DatasetVersion(BaseModel):
    """Metadata for a registered dataset version.

    Attributes:
        version: Unique version identifier (e.g., 'silver_v1').
        checksum: SHA-256 hex digest of the dataset content.
        created_at: ISO-8601 timestamp of version creation.
        model: LLM model used for generation (e.g., 'qwen3.5:27b').
        prompt_version: Version of the generation prompt used.
        total_cases: Total number of cases in this version.
        description: Optional human-readable description.
    """

    version: str
    checksum: str
    created_at: str
    model: str
    prompt_version: str
    total_cases: int
    description: str = ""


class VersionRegistry:
    """Maps version identifiers to checksums and metadata.

    Provides registration, lookup, and listing of dataset versions
    to support integrity validation in the loader.
    """

    def __init__(self) -> None:
        self._versions: dict[str, DatasetVersion] = {}

    def register(self, version: DatasetVersion) -> None:
        """Register a new dataset version.

        Args:
            version: DatasetVersion instance to register.

        Raises:
            ValueError: If version identifier is already registered.
        """
        if version.version in self._versions:
            raise ValueError(
                f"Version '{version.version}' is already registered."
            )
        self._versions[version.version] = version

    def get(self, version_id: str) -> DatasetVersion | None:
        """Retrieve a registered version by its identifier.

        Args:
            version_id: The version identifier to look up.

        Returns:
            DatasetVersion if found, None otherwise.
        """
        return self._versions.get(version_id)

    def exists(self, version_id: str) -> bool:
        """Check whether a version identifier is registered.

        Args:
            version_id: The version identifier to check.

        Returns:
            True if registered, False otherwise.
        """
        return version_id in self._versions

    def list_versions(self) -> list[str]:
        """List all registered version identifiers.

        Returns:
            Sorted list of version identifier strings.
        """
        return sorted(self._versions.keys())
