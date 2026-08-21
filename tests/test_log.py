import logging

from kcq.utils.log import get_logger


def test_get_logger_returns_same_logger_instance():
    logger_a = get_logger("kcq.test.same")
    logger_b = get_logger("kcq.test.same")
    assert logger_a is logger_b


def test_get_logger_does_not_stack_duplicate_handlers():
    get_logger("kcq.test.nodupe")
    handler_count_after_first = len(logging.getLogger("kcq.test.nodupe").handlers)
    get_logger("kcq.test.nodupe")
    handler_count_after_second = len(logging.getLogger("kcq.test.nodupe").handlers)
    assert handler_count_after_first == handler_count_after_second


def test_logging_never_raises_even_without_a_klayout_gui(caplog):
    logger = get_logger("kcq.test.nogui")
    # Headless (`klayout` PyPI package / batch mode): pya has no
    # Application, so the GUI handler must fail silently rather than
    # propagate out of logger calls.
    logger.warning("this must not raise even though there is no GUI")
    logger.info("info message")
