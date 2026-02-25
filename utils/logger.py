"""Structured logging setup for local dev and Docker."""
import logging
import sys
import structlog


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog + stdlib logging.

    - TTY (local dev): colored key=value output
    - No TTY (Docker): JSON per line, ready for log aggregators
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    is_tty = sys.stdout.isatty()

    if is_tty:
        # Human-readable for local dev
        structlog.configure(
            processors=shared_processors + [structlog.dev.ConsoleRenderer()],
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
        stdlib_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(stdlib_formatter)
    else:
        # JSON for Docker / production
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
                foreign_pre_chain=shared_processors,
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str = "app") -> structlog.BoundLogger:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)
