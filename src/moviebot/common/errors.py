from enum import StrEnum


class Status(StrEnum):
    """Estados funcionales del sistema."""

    SUCCESS = "SUCCESS"
    NO_RESULTS = "NO_RESULTS"
    DATASOURCE_ERROR = "DATASOURCE_ERROR"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


class MovieBotError(Exception):
    """Excepción base para errores del sistema MovieBot."""
