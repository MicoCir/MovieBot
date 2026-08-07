import logging


def configure_logging(log_level: str) -> None:
    """Configura handlers y formatters del logging root.

    Debe invocarse UNA SOLA VEZ desde el composition root:
        settings = Settings()
        configure_logging(settings.log_level)
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger con el nombre indicado.

    NO instancia Settings ni lee variables de entorno.
    """
    return logging.getLogger(name)
