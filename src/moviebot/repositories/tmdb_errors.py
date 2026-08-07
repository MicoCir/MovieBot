"""Jerarquía de excepciones para el conector TMDB."""

from moviebot.common.errors import MovieBotError


class TmdbError(MovieBotError):
    """Base para errores del conector TMDB."""

    def __init__(self, message: str, operation: str) -> None:
        self.message = message
        self.operation = operation
        super().__init__(message)


class TmdbHttpError(TmdbError):
    """Error HTTP (4xx/5xx) de la API TMDB."""

    def __init__(
        self,
        message: str,
        operation: str,
        status_code: int,
        response_body: str,
    ) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(message, operation)


class TmdbTimeoutError(TmdbError):
    """Timeout al conectar con TMDB."""


class TmdbConnectionError(TmdbError):
    """Fallo de red/DNS al conectar con TMDB."""


class TmdbInvalidResponseError(TmdbError):
    """Respuesta no parseable o estructura inválida."""


class TmdbFixtureConflictError(TmdbError):
    """Ya existe un fixture con el mismo nombre de versión."""


class TmdbFixtureInconsistentError(TmdbError):
    """Estado inconsistente: existe uno de los archivos del fixture pero no el otro."""
