from threading import Lock

from loguru import logger
from redis import Redis
from redis.exceptions import RedisError

from app.config import Config

_client = None
_redis_lock = Lock()


def _build_client() -> Redis | None:
    if not Config.REDIS_ENABLED:
        return None
    return Redis.from_url(
        Config.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
    )


def get_redis_client() -> Redis | None:
    global _client
    if not Config.REDIS_ENABLED:
        return None

    if _client is None:
        with _redis_lock:
            if _client is None:
                _client = _build_client()
                logger.info("Redis client initialized")
    return _client


def init_redis(app=None):
    client = get_redis_client()
    if client is None:
        logger.info("Redis integration disabled by configuration")
        return None

    try:
        client.ping()
        if app is not None:
            app.extensions["redis_client"] = client
        logger.info("Redis integration ready")
        return client
    except RedisError as exc:
        logger.error("Redis initialization failed: {}", exc)
        return None


def check_redis_connection() -> tuple[bool, str | None]:
    if not Config.REDIS_ENABLED:
        return True, "disabled"

    client = get_redis_client()
    if client is None:
        return False, "client unavailable"

    try:
        client.ping()
        return True, None
    except RedisError as exc:
        logger.warning("Redis health check failed: {}", exc)
        return False, str(exc)
