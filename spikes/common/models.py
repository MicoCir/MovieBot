"""Shared Pydantic models for spike results."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ViabilityStatus(str, Enum):
    """Viability status for a spike execution."""

    CONFIRMED = "confirmed"
    BLOCKED = "blocked"


class SpikeResult(BaseModel):
    """Base result model for all spike executions."""

    spike_name: str
    executed_at: datetime
    status: ViabilityStatus
    duration_seconds: float
    artifacts_produced: list[str]
    errors: list[str]
