import sys
from pathlib import Path

from loguru import logger

from app.config import Config


def setup_logger():
    if getattr(setup_logger, "_configured", False):
        return logger

    logger.remove()

    logger.add(
        sys.stdout,
        level=Config.LOG_LEVEL,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}",
    )

    log_dir = Path(Config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "app.log",
        level="INFO",
        enqueue=True,
        rotation="5 MB",
        retention="14 days",
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}",
    )

    setup_logger._configured = True
    logger.info("Application logging configured at {} level", Config.LOG_LEVEL)
    return logger
