import logging
import logging.handlers
import sys

import structlog
from pydantic_settings import SettingsConfigDict

from settings import BaseProjectSettings

LOG_DIR = BaseProjectSettings.PROJECT_ROOT_DIR / "logs"


class LoggingSettings(BaseProjectSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=(".env.defaults", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # File logging (logs/leetcode_pipeline.log) always happens regardless of
    # this — it's the durable record. This only controls whether the same
    # events are *also* echoed live to the terminal, which gets noisy during
    # a big batch run (populate --all, notes prefill --all, ...).
    CONSOLE_ENABLED: bool = True


logging_settings = LoggingSettings()


def configure_logging(level: int = logging.INFO) -> None:
    """Sets up rotating JSON file logging, plus console (colored,
    human-readable) logging unless LOG_CONSOLE_ENABLED=false.
    Call this once, at your pipeline's entrypoint, before anything else runs.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # --- Shared pre-processing chain (runs before either renderer) ----
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]

    # --- Handlers -----------------------------------------------------
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "leetcode_pipeline.log",
        when="midnight",
        backupCount=5,  # keeps 5 days of rotated logs, deletes older ones
        encoding="utf-8",
    )
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
    )

    handlers = [file_handler]

    if logging_settings.CONSOLE_ENABLED:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processor=structlog.dev.ConsoleRenderer(),
                foreign_pre_chain=shared_processors,
            )
        )
        handlers.append(console_handler)

    # --- Wire handlers into the root logger ----------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = []  # avoid duplicate handlers if called twice
    for handler in handlers:
        root_logger.addHandler(handler)

    # --- Tell structlog to route through the stdlib logging above -----
    structlog.configure(
        processors=shared_processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
