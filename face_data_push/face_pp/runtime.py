import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_logger(name: str, log_file: str):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def connect_mqtt(client, host, port, logger, *, max_retries=10, retry_delay=5):
    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Connecting to MQTT broker %s:%s (attempt %d/%d)", host, port, attempt, max_retries)
            client.connect(host, port, 60)
            logger.info("Connected to MQTT broker.")
            return True
        except Exception as exc:
            logger.warning("MQTT connection failed on attempt %d/%d: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(retry_delay)

    logger.error("Unable to connect to MQTT broker after %d attempts.", max_retries)
    return False
