"""Pydantic models for Meilisearch spike results."""

from spikes.common.models import SpikeResult


class MeilisearchSpikeResult(SpikeResult):
    """Result model for the Meilisearch CE viability spike."""

    image_tag: str
    container_digest: str | None = None
    healthcheck_passed: bool
    capabilities_tested: dict[str, bool]  # capability -> passed
    enterprise_features_detected: list[str]
