from loguru import logger
import os
import sys

def setup_logger():
    # Remove default handlers (to avoid duplicates)
    logger.remove()

    # Set log level based on environment
    log_level = "DEBUG" if os.getenv("FLASK_ENV") == "development" else "INFO"

    # Log to stdout (good for Docker and dev)
    logger.add(sys.stdout, level=log_level, format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}")

    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)

    # Log to file with rotation (keep logs small and fresh)
    logger.add(
        "logs/app.log",
        rotation="1 MB",           # Rotate when file > 1 MB
        retention="7 days",        # Keep logs for 7 days
        level="INFO",
        serialize=False            # Set to True if using with log shipping tools like Fluent Bit
    )

    # Confirmation message on startup
    logger.info("Logger initialized")

