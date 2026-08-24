---
name: structlog-logging
description: Add or update structured logging in a Python file using structlog. Use when the user asks to "add logs", "add logging", "instrument this function with logs", or mentions structlog, slug-based logging, or per-stage logging in this DSA pipeline.
---

# structlog-logging

Add structlog-based logging to the target file(s), following these rules exactly:

1. Import as: `import structlog` then `logger = structlog.get_logger(__name__)`
   — never `import logging; logging.getLogger(__name__)`.
2. If the function operates on a single `slug`, bind it at the top:
   `log = logger.bind(slug=slug, stage="<stage_name>")`
   then use `log.info(...)` for the rest of that function instead of the module-level `logger`.
3. Event names: `snake_case`, past tense for completed states
   (`metadata_fetch_succeeded`, `metadata_fetch_failed`), present/gerund for in-progress
   (`metadata_fetch_started`).
4. Never use f-strings in log calls. Pass fields as kwargs:
   GOOD: `log.info("metadata_fetch_succeeded", question_id=question_record.id)`
   BAD:  `log.info(f"Successfully populated metadata for '{slug}'")`
5. Use `log.warning(...)` for recoverable/expected failures (e.g. no data found),
   `log.error(...)` or `log.exception(...)` for actual exceptions.
6. Don't touch `logging_config.py` unless explicitly asked — that file owns
   handler/formatter setup and shouldn't be duplicated per-module.
