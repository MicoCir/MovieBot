import logging

from moviebot.common.logging import configure_logging


def test_configure_logging_is_idempotent_and_uses_contract_format():
    root_logger = logging.getLogger()
    previous_handlers = root_logger.handlers[:]
    previous_level = root_logger.level

    try:
        configure_logging("DEBUG")
        first_handlers = root_logger.handlers[:]

        configure_logging("INFO")
        second_handlers = root_logger.handlers[:]

        assert len(first_handlers) == len(second_handlers) == 1
        assert second_handlers[0].formatter is not None
        assert (
            second_handlers[0].formatter._fmt
            == "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        )
        assert root_logger.level == logging.INFO
    finally:
        root_logger.handlers.clear()
        root_logger.handlers.extend(previous_handlers)
        root_logger.setLevel(previous_level)
