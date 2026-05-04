"""
Structured logging configuration.

`setup_logging()` configures structlog + the stdlib root logger so all
existing `logging.getLogger(...)` callers keep working but their output is
formatted by structlog (pretty in dev, JSON in prod).
"""

import logging

import structlog

from app.core.settings import loggingsettings

_LEVEL_MAP = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

_initialised = False


def setup_logging() -> None:
    """Configure structlog + root logger. Idempotent."""
    global _initialised
    if _initialised:
        return

    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logs_render = (
        structlog.processors.JSONRenderer()
        if loggingsettings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    handler = logging.StreamHandler()
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            logs_render,
        ],
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Replace any pre-existing handlers so we don't double-log.
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    root_logger.addHandler(handler)
    root_logger.setLevel(
        _LEVEL_MAP.get(loggingsettings.log_level.lower(), logging.INFO)
    )

    for _name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(_name).handlers.clear()
        logging.getLogger(_name).propagate = True

    _initialised = True


setup_logging()


log = structlog.get_logger("chat-api").bind(environment=loggingsettings.environment)
log.info(
    "logging_initialized",
    log_level=loggingsettings.log_level,
    log_format=loggingsettings.log_format,
)
