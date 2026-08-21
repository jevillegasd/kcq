"""Logging setup for kcq.

Every kcq module calls get_logger(__name__) instead of using print().
Works both inside the KLayout GUI (mirrors records to KLayout's own log/
message facilities) and headless (klayout -b -r script.py, or the
standalone `klayout` PyPI package used by the test suite), where only the
stderr stream handler is available.
"""

import logging
import sys

_CONFIGURED_LOGGERS = set()

try:
    import pya
except ImportError:  # pragma: no cover - exercised only outside KLayout
    pya = None


class _KLayoutHandler(logging.Handler):
    """Forwards records to KLayout's main window message/status area.

    Only instantiated when a GUI Application with a main_window() is
    actually present; falls back silently (no-op) otherwise, since a
    headless Application (batch mode, `klayout -b`) has no main_window.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            app = pya.Application.instance()
            main_window = app.main_window() if app is not None else None
            if main_window is None:
                return
            main_window.message(self.format(record), 3000)
        except Exception:
            # Logging must never raise -- a broken GUI handler should not
            # take down the caller.
            pass


def get_logger(name: str) -> logging.Logger:
    """Returns a configured logging.Logger for `name`.

    Idempotent: repeated calls with the same name return the same logger
    without stacking duplicate handlers.
    """
    logger = logging.getLogger(name)
    if name in _CONFIGURED_LOGGERS:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[kcq] %(name)s: %(levelname)s: %(message)s")

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if pya is not None:
        gui_handler = _KLayoutHandler()
        gui_handler.setFormatter(formatter)
        gui_handler.setLevel(logging.WARNING)
        logger.addHandler(gui_handler)

    logger.propagate = False
    _CONFIGURED_LOGGERS.add(name)
    return logger
