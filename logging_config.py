import logging
import logging.handlers
import sys

import structlog

from settings import BaseProjectSettings

LOG_DIR = BaseProjectSettings.PROJECT_ROOT_DIR / "logs"


def configure_logging(level: int = logging.INFO) -> None:
    """Sets up console (colored, human-readable) + rotating JSON file logging.
    Call this once, at your pipeline's entrypoint, before anything else runs.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # --- Handlers -----------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "leetcode_pipeline.log",
        when="midnight",
        backupCount=5,  # keeps 5 days of rotated logs, deletes older ones
        encoding="utf-8",
    )

    # --- Shared pre-processing chain (runs before either renderer) ----
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    # --- Formatters: JSON for file, colored text for console ----------
    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
        foreign_pre_chain=shared_processors,
    )

    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)

    # --- Wire handlers into the root logger ----------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = []  # avoid duplicate handlers if called twice
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # --- Tell structlog to route through the stdlib logging above -----
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
